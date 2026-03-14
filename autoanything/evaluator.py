from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import EvaluatorConfig, ProblemDefinition

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL,
    branch TEXT NOT NULL,
    score REAL,
    status TEXT NOT NULL,
    description TEXT,
    submitted_at TEXT,
    evaluated_at TEXT,
    duration_seconds REAL,
    error_message TEXT,
    metrics_json TEXT,
    feedback_json TEXT,
    patch_summary_json TEXT
);
CREATE TABLE IF NOT EXISTS incumbent (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    commit_sha TEXT NOT NULL,
    score REAL NOT NULL,
    promoted_at TEXT NOT NULL,
    branch TEXT NOT NULL,
    description TEXT,
    metrics_json TEXT
);
"""


@dataclass(slots=True)
class BranchCandidate:
    branch: str
    ref_name: str
    commit_sha: str
    submitted_at: str
    description: str


@dataclass(slots=True)
class ScoreRun:
    status: str
    score: float | None
    duration_seconds: float
    metrics: dict[str, Any]
    error_message: str | None
    feedback: dict[str, Any]


class LocalEvaluator:
    def __init__(self, config: EvaluatorConfig | Path):
        if isinstance(config, Path):
            config = EvaluatorConfig.from_file(config)
        self.config = config
        self.problem = ProblemDefinition.from_file(self.config.problem_path)
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.private_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.result_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.history_json_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.config.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _git(
        self,
        *args: str,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.config.repo_root),
            text=True,
            capture_output=True,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc

    def _shell(self, command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["AUTOANYTHING_REPO_ROOT"] = str(self.config.repo_root)
        env["AUTOANYTHING_PROBLEM_NAME"] = self.problem.name
        return subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            shell=True,
            executable=self.config.score_shell,
            env=env,
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _remote_exists(self) -> bool:
        return self._git("remote", "get-url", "origin", check=False).returncode == 0

    def _fetch_if_configured(self) -> None:
        if self.config.fetch_remote and self._remote_exists():
            self._git("fetch", "origin", "--prune")

    def _current_branch(self) -> str:
        proc = self._git("symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        return proc.stdout.strip()

    def _checkout_base(self) -> None:
        if self._current_branch() != self.config.base_branch:
            self._git("checkout", self.config.base_branch)

    def _incumbent(self) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM incumbent WHERE id = 1").fetchone()

    def _evaluated_shas(self) -> set[str]:
        with self._connect() as conn:
            return {row[0] for row in conn.execute("SELECT commit_sha FROM evaluations")}

    def _agent_score(self, branch: str) -> tuple[float, int]:
        parts = branch.split("/")
        agent = parts[1] if len(parts) > 1 else branch
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status FROM evaluations WHERE branch LIKE ?",
                (f"proposals/{agent}/%",),
            ).fetchall()
        accepted = sum(1 for row in rows if row[0] == "accepted")
        total = len(rows)
        return (accepted / total if total else 0.0, accepted)

    def _discover_candidates(self) -> list[BranchCandidate]:
        self._fetch_if_configured()
        seen = self._evaluated_shas()
        proc = self._git(
            "for-each-ref",
            "--format=%(refname)\t%(refname:short)\t%(objectname)\t%(committerdate:iso8601)",
            "refs/heads",
            "refs/remotes/origin",
        )
        by_branch: dict[str, BranchCandidate] = {}
        for line in proc.stdout.splitlines():
            ref_name, short_name, commit_sha, submitted_at = line.split("\t")
            normalized = short_name.removeprefix("origin/")
            if normalized == self.config.base_branch:
                continue
            if not any(normalized.startswith(prefix) for prefix in self.config.proposal_prefixes):
                continue
            if commit_sha in seen:
                continue
            description = self._git("show", "-s", "--format=%s", commit_sha).stdout.strip()
            candidate = BranchCandidate(normalized, ref_name, commit_sha, submitted_at, description)
            current = by_branch.get(normalized)
            if current is None or ref_name.startswith("refs/remotes/"):
                by_branch[normalized] = candidate

        candidates = list(by_branch.values())
        if self.config.queue_policy == "agent_priority":
            candidates.sort(
                key=lambda item: (
                    *(-value for value in self._agent_score(item.branch)),
                    item.submitted_at,
                    item.branch,
                )
            )
        else:
            candidates.sort(key=lambda item: (item.submitted_at, item.branch))
        return candidates

    def _merge_base(self, commit_sha: str) -> str:
        return self._git("merge-base", commit_sha, self.config.base_branch).stdout.strip()

    def _base_ahead_count(self, commit_sha: str) -> int:
        merge_base = self._merge_base(commit_sha)
        proc = self._git("rev-list", "--count", f"{merge_base}..{self.config.base_branch}")
        return int(proc.stdout.strip() or "0")

    def _patch_summary(self, candidate: BranchCandidate) -> dict[str, Any]:
        merge_base = self._merge_base(candidate.commit_sha)
        numstat = self._git(
            "diff",
            "--numstat",
            f"{merge_base}..{candidate.commit_sha}",
        ).stdout.splitlines()
        files: list[dict[str, Any]] = []
        insertions = 0
        deletions = 0
        for line in numstat:
            if not line.strip():
                continue
            added, removed, path = line.split("\t", 2)
            add_count = 0 if added == "-" else int(added)
            del_count = 0 if removed == "-" else int(removed)
            files.append({"path": path, "insertions": add_count, "deletions": del_count})
            insertions += add_count
            deletions += del_count
        diff_text = self._git(
            "diff",
            "--unified=1",
            f"{merge_base}..{candidate.commit_sha}",
        ).stdout
        return {
            "files": files,
            "insertions": insertions,
            "deletions": deletions,
            "diff": diff_text[:12000],
        }

    def _parse_value(self, regex: str, text: str) -> Any | None:
        match = re.search(regex, text, re.MULTILINE)
        if not match:
            return None
        value = match.groupdict().get("value") if match.groupdict() else match.group(1)
        if value is None:
            return None
        value = value.strip()
        try:
            if any(ch in value.lower() for ch in (".", "e")):
                return float(value)
            return int(value)
        except ValueError:
            return value

    def _render_result_json(self, candidate: BranchCandidate, run: ScoreRun) -> None:
        payload = {
            "branch": candidate.branch,
            "commit_sha": candidate.commit_sha,
            "status": run.status,
            "score": run.score,
            "duration_seconds": run.duration_seconds,
            "metrics": run.metrics,
            "error_message": run.error_message,
            "feedback": run.feedback,
        }
        self.config.result_path.write_text(json.dumps(payload, indent=2) + "\n")

    def _score_candidate(self, candidate: BranchCandidate, *, merge_on_top: bool) -> ScoreRun:
        worktree_root = self.config.db_path.parent / "worktrees"
        worktree_root.mkdir(parents=True, exist_ok=True)
        worktree_path = worktree_root / f"{candidate.branch.replace('/', '-')}-{candidate.commit_sha[:7]}"
        if worktree_path.exists():
            shutil.rmtree(worktree_path)

        base_ref = self.config.base_branch if merge_on_top else candidate.commit_sha
        self._git("worktree", "add", "--detach", str(worktree_path), base_ref)
        try:
            if merge_on_top:
                merge_proc = self._git(
                    "merge",
                    "--no-commit",
                    "--no-ff",
                    candidate.ref_name,
                    cwd=worktree_path,
                    check=False,
                )
                if merge_proc.returncode != 0:
                    combined = (merge_proc.stdout or "") + (
                        "\n" if merge_proc.stdout and merge_proc.stderr else ""
                    ) + (merge_proc.stderr or "")
                    self.config.private_log_path.write_text(combined)
                    run = ScoreRun(
                        status="rejected",
                        score=None,
                        duration_seconds=0.0,
                        metrics={},
                        error_message=combined.strip() or "Merge conflict while preparing evaluation",
                        feedback={
                            "summary": "Proposal could not be cleanly rebased onto the incumbent state.",
                            "reason": "merge-conflict",
                        },
                    )
                    self._render_result_json(candidate, run)
                    return run

            t0 = time.time()
            proc = self._shell(self.config.score_command, worktree_path)
            duration = time.time() - t0
            combined = (proc.stdout or "") + (
                "\n" if proc.stdout and proc.stderr else ""
            ) + (proc.stderr or "")
            self.config.private_log_path.write_text(combined)

            if proc.returncode != 0:
                tail = "\n".join(combined.splitlines()[-20:])
                run = ScoreRun(
                    status="crash",
                    score=None,
                    duration_seconds=duration,
                    metrics={},
                    error_message=tail or f"Command exited with status {proc.returncode}",
                    feedback={
                        "summary": "Scoring command crashed.",
                        "exit_code": proc.returncode,
                    },
                )
                self._render_result_json(candidate, run)
                return run

            score_value = self._parse_value(self.config.score_regex, combined)
            if score_value is None:
                run = ScoreRun(
                    status="crash",
                    score=None,
                    duration_seconds=duration,
                    metrics={},
                    error_message="Unable to parse a score from evaluator output.",
                    feedback={
                        "summary": "Scoring command ran but did not emit a parseable score.",
                    },
                )
                self._render_result_json(candidate, run)
                return run

            metrics: dict[str, Any] = {}
            for metric in self.config.metrics:
                parsed = self._parse_value(metric.regex, combined)
                if parsed is not None:
                    metrics[metric.name] = parsed

            run = ScoreRun(
                status="scored",
                score=float(score_value),
                duration_seconds=duration,
                metrics=metrics,
                error_message=None,
                feedback={"summary": "Score parsed successfully."},
            )
            self._render_result_json(candidate, run)
            return run
        finally:
            self._git("worktree", "remove", "--force", str(worktree_path), check=False)

    def _record_evaluation(
        self,
        candidate: BranchCandidate,
        *,
        status: str,
        score: float | None,
        duration_seconds: float,
        error_message: str | None,
        metrics: dict[str, Any],
        feedback: dict[str, Any],
        patch_summary: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluations (
                    commit_sha, branch, score, status, description, submitted_at,
                    evaluated_at, duration_seconds, error_message, metrics_json,
                    feedback_json, patch_summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.commit_sha,
                    candidate.branch,
                    score,
                    status,
                    candidate.description,
                    candidate.submitted_at,
                    self._now(),
                    duration_seconds,
                    error_message,
                    json.dumps(metrics, sort_keys=True),
                    json.dumps(feedback, sort_keys=True),
                    json.dumps(patch_summary, sort_keys=True),
                ),
            )
            conn.commit()

    def _set_incumbent(
        self,
        commit_sha: str,
        score: float,
        branch: str,
        description: str,
        metrics: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO incumbent (id, commit_sha, score, promoted_at, branch, description, metrics_json)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    commit_sha = excluded.commit_sha,
                    score = excluded.score,
                    promoted_at = excluded.promoted_at,
                    branch = excluded.branch,
                    description = excluded.description,
                    metrics_json = excluded.metrics_json
                """,
                (
                    commit_sha,
                    score,
                    self._now(),
                    branch,
                    description,
                    json.dumps(metrics, sort_keys=True),
                ),
            )
            conn.commit()

    def _merge_candidate_into_base(self, candidate: BranchCandidate) -> str:
        self._checkout_base()
        merge_proc = self._git("merge", "--no-ff", "--no-edit", candidate.ref_name, check=False)
        if merge_proc.returncode != 0:
            self._git("merge", "--abort", check=False)
            raise RuntimeError(
                merge_proc.stderr.strip()
                or merge_proc.stdout.strip()
                or "Failed to merge accepted proposal"
            )
        return self._git("rev-parse", self.config.base_branch).stdout.strip()

    def _artifact_paths(self) -> list[Path]:
        return [
            self.config.leaderboard_path,
            self.config.history_json_path,
            self.config.dashboard_path,
            self.config.signals_markdown_path,
            self.config.signals_json_path,
        ]

    def _maybe_commit_public_artifacts(self, message: str) -> None:
        if not self.config.commit_public_artifacts:
            return
        self._checkout_base()
        rels = [
            path.relative_to(self.config.repo_root).as_posix()
            for path in self._artifact_paths()
            if path.exists()
        ]
        if not rels:
            return
        status = self._git("status", "--short", "--", *rels)
        if not status.stdout.strip():
            return
        self._git("add", "--", *rels)
        commit_proc = self._git("commit", "-m", message, check=False)
        if commit_proc.returncode != 0 and "nothing to commit" not in (
            commit_proc.stdout + commit_proc.stderr
        ):
            raise RuntimeError(commit_proc.stderr.strip() or commit_proc.stdout.strip())
        if self.config.push_after_update and self._remote_exists():
            self._git("push", "origin", self.config.base_branch)

    def _format_score(self, score: float | None) -> str:
        return "crash" if score is None else f"{score:.6f}"

    def _load_evaluations(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evaluations ORDER BY evaluated_at DESC, id DESC"
            ).fetchall()
        evaluations: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for field in ("metrics_json", "feedback_json", "patch_summary_json"):
                value = item.pop(field)
                item[field.removesuffix("_json")] = json.loads(value) if value else {}
            evaluations.append(item)
        return evaluations

    def _signal_payload(self, evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        recent = [
            item
            for item in evaluations
            if item["status"] != "baseline"
        ][: self.config.max_recent_failures_for_signal]
        if recent and all(item["status"] in {"rejected", "crash"} for item in recent):
            return {
                "recent_failures": len(recent),
                "status": "stalled",
                "message": (
                    f"The last {len(recent)} proposals all failed to improve the incumbent. "
                    "Try a radical strategy."
                ),
            }
        if evaluations:
            return {
                "recent_failures": sum(
                    1 for item in recent if item["status"] in {"rejected", "crash"}
                ),
                "status": "active",
                "message": "The search is active. Read the recent history before proposing the next change.",
            }
        return {
            "recent_failures": 0,
            "status": "cold-start",
            "message": "No evaluator signals have been published yet.",
        }

    def export_public_artifacts(self) -> None:
        evaluations = self._load_evaluations()
        accepted = [
            item for item in evaluations if item["status"] in {"baseline", "accepted"}
        ]
        accepted.sort(
            key=lambda item: item["score"] if item["score"] is not None else float("inf"),
            reverse=self.problem.score.leaderboard_reverse(),
        )

        lines = [
            "# Leaderboard",
            "",
            "| # | Score | Branch | Description | When |",
            "|---|-------|--------|-------------|------|",
        ]
        if accepted:
            for index, item in enumerate(accepted[:20], start=1):
                lines.append(
                    f"| {index} | {self._format_score(item['score'])} | "
                    f"{item['branch']} | {item['description'] or ''} | {item['evaluated_at'] or ''} |"
                )
        else:
            lines.append("| - | - | - | No accepted evaluations yet | - |")
        lines.extend(
            [
                "",
                "## Recent Attempts",
                "",
                "| Score | Status | Branch | Description | When |",
                "|-------|--------|--------|-------------|------|",
            ]
        )
        if evaluations:
            for item in evaluations[:20]:
                lines.append(
                    f"| {self._format_score(item['score'])} | {item['status']} | "
                    f"{item['branch']} | {item['description'] or ''} | {item['evaluated_at'] or ''} |"
                )
        else:
            lines.append("| - | - | - | No attempts yet | - |")
        self.config.leaderboard_path.write_text("\n".join(lines) + "\n")

        self.config.history_json_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.history_json_path.write_text(json.dumps(evaluations, indent=2) + "\n")

        points = [item["score"] for item in reversed(accepted) if item["score"] is not None]
        chart = "<p>No accepted evaluations yet.</p>"
        if points:
            lo, hi = min(points), max(points)
            span = hi - lo or 1.0
            coords: list[str] = []
            for index, point in enumerate(points):
                x = 40 + index * (320 / max(len(points) - 1, 1))
                y = 180 - ((point - lo) / span) * 120
                coords.append(f"{x:.1f},{y:.1f}")
            chart = (
                "<svg width='420' height='220' viewBox='0 0 420 220' role='img' aria-label='score chart'>"
                "<rect x='0' y='0' width='420' height='220' fill='#f9fafb' stroke='#d1d5db'/>"
                "<polyline fill='none' stroke='#2563eb' stroke-width='3' points='"
                + " ".join(coords)
                + "'/></svg>"
            )

        rows = "".join(
            f"<tr><td>{self._format_score(item['score'])}</td>"
            f"<td>{item['status']}</td><td>{item['branch']}</td>"
            f"<td>{item['description'] or ''}</td></tr>"
            for item in evaluations[:20]
        )
        dashboard = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>AutoAnything Dashboard</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #d1d5db; padding: 0.5rem; text-align: left; }}
    th {{ background: #f3f4f6; }}
    .chart {{ margin: 1rem 0 2rem; }}
  </style>
</head>
<body>
  <h1>AutoAnything Dashboard</h1>
  <p>Problem: {self.problem.name}</p>
  <div class='chart'>{chart}</div>
  <h2>Recent Attempts</h2>
  <table>
    <thead><tr><th>Score</th><th>Status</th><th>Branch</th><th>Description</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""
        self.config.dashboard_path.write_text(dashboard)

        signal = self._signal_payload(evaluations)
        self.config.signals_json_path.write_text(json.dumps(signal, indent=2) + "\n")
        self.config.signals_markdown_path.write_text(
            "# Search Signals\n\n"
            f"- Status: **{signal['status']}**\n"
            f"- Recent failures: **{signal['recent_failures']}**\n"
            f"- Message: {signal['message']}\n"
        )

    def ensure_baseline(self) -> dict[str, Any] | None:
        incumbent = self._incumbent()
        if incumbent is not None:
            return dict(incumbent)

        self._checkout_base()
        commit_sha = self._git("rev-parse", self.config.base_branch).stdout.strip()
        submitted_at = self._git("show", "-s", "--format=%cI", commit_sha).stdout.strip()
        description = self._git("show", "-s", "--format=%s", commit_sha).stdout.strip()
        candidate = BranchCandidate(
            self.config.base_branch,
            f"refs/heads/{self.config.base_branch}",
            commit_sha,
            submitted_at,
            description,
        )
        run = self._score_candidate(candidate, merge_on_top=False)
        if run.status == "crash" or run.score is None:
            raise RuntimeError(f"Baseline evaluation failed: {run.error_message}")

        self._record_evaluation(
            candidate,
            status="baseline",
            score=run.score,
            duration_seconds=run.duration_seconds,
            error_message=run.error_message,
            metrics=run.metrics,
            feedback=run.feedback,
            patch_summary={"files": [], "insertions": 0, "deletions": 0, "diff": ""},
        )
        self._set_incumbent(
            commit_sha,
            run.score,
            candidate.branch,
            candidate.description,
            run.metrics,
        )
        self.export_public_artifacts()
        self._maybe_commit_public_artifacts(f"evaluator: record baseline {commit_sha[:7]}")
        return dict(self._incumbent() or {})

    def evaluate_once(self) -> dict[str, Any] | None:
        self.ensure_baseline()
        candidates = self._discover_candidates()
        if not candidates:
            return None

        candidate = candidates[0]
        patch_summary = self._patch_summary(candidate)
        if self.config.stale_after_base_commits is not None:
            ahead = self._base_ahead_count(candidate.commit_sha)
            if ahead > self.config.stale_after_base_commits:
                feedback = {
                    "summary": "Branch was discarded before scoring because it was too stale.",
                    "reason": "stale-branch",
                    "base_ahead_commits": ahead,
                }
                self._record_evaluation(
                    candidate,
                    status="rejected",
                    score=None,
                    duration_seconds=0.0,
                    error_message=f"Base branch advanced {ahead} commits beyond merge-base.",
                    metrics={},
                    feedback=feedback,
                    patch_summary=patch_summary,
                )
                self.export_public_artifacts()
                self._maybe_commit_public_artifacts(f"evaluator: reject stale {candidate.branch}")
                return {"branch": candidate.branch, "status": "rejected", "score": None}

        incumbent = self._incumbent()
        incumbent_score = float(incumbent["score"]) if incumbent is not None else None
        incumbent_metrics = (
            json.loads(incumbent["metrics_json"])
            if incumbent and incumbent["metrics_json"]
            else {}
        )

        run = self._score_candidate(candidate, merge_on_top=self.config.rebase_before_score)
        status = run.status
        feedback = dict(run.feedback)
        if status == "scored" and run.score is not None:
            delta = run.score - incumbent_score if incumbent_score is not None else 0.0
            better = self.problem.score.better(run.score, incumbent_score)
            status = "accepted" if better else "rejected"
            feedback.update(
                {
                    "summary": (
                        "Proposal improved the incumbent and was promoted."
                        if better
                        else "Proposal did not beat the incumbent."
                    ),
                    "score_delta": delta,
                    "incumbent_score": incumbent_score,
                }
            )
            if "peak_vram_mb" in run.metrics and "peak_vram_mb" in incumbent_metrics:
                feedback["peak_vram_delta_mb"] = (
                    run.metrics["peak_vram_mb"] - incumbent_metrics["peak_vram_mb"]
                )

        self._record_evaluation(
            candidate,
            status=status,
            score=run.score,
            duration_seconds=run.duration_seconds,
            error_message=run.error_message,
            metrics=run.metrics,
            feedback=feedback,
            patch_summary=patch_summary,
        )
        if status == "accepted" and run.score is not None:
            promoted_sha = self._merge_candidate_into_base(candidate)
            self._set_incumbent(
                promoted_sha,
                run.score,
                candidate.branch,
                candidate.description,
                run.metrics,
            )

        self.export_public_artifacts()
        self._maybe_commit_public_artifacts(
            f"evaluator: publish {status} result for {candidate.branch}"
        )
        return {"branch": candidate.branch, "status": status, "score": run.score}

    def loop(self, *, once: bool = False) -> int:
        while True:
            result = self.evaluate_once()
            if once:
                return 0
            if result is None:
                time.sleep(self.config.poll_seconds)
