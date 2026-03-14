from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha       TEXT NOT NULL,
    branch           TEXT NOT NULL,
    score            REAL,
    status           TEXT NOT NULL,
    description      TEXT,
    submitted_at     TEXT,
    evaluated_at     TEXT,
    duration_seconds REAL,
    error_message    TEXT,
    metrics_json     TEXT
);

CREATE TABLE IF NOT EXISTS incumbent (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    commit_sha   TEXT NOT NULL,
    score        REAL NOT NULL,
    promoted_at  TEXT NOT NULL
);
"""


@dataclass
class CandidateRef:
    sort_key: int
    refname: str
    branch: str
    sha: str


@dataclass
class ScoreResult:
    ok: bool
    score: float | None
    metrics: dict[str, Any]
    error_message: str | None
    duration_seconds: float


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(command: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({' '.join(command)}):\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def git(repo_root: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd=repo_root, check=check).stdout.strip()


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def load_incumbent(conn: sqlite3.Connection) -> tuple[str, float] | None:
    row = conn.execute("SELECT commit_sha, score FROM incumbent WHERE id = 1").fetchone()
    if not row:
        return None
    return row[0], float(row[1])


def already_evaluated(conn: sqlite3.Connection, branch: str, sha: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM evaluations WHERE branch = ? AND commit_sha = ? LIMIT 1",
        (branch, sha),
    ).fetchone()
    return row is not None


def insert_evaluation(
    conn: sqlite3.Connection,
    *,
    commit_sha: str,
    branch: str,
    score: float | None,
    status: str,
    description: str,
    submitted_at: str,
    evaluated_at: str,
    duration_seconds: float,
    error_message: str | None,
    metrics: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO evaluations (
            commit_sha, branch, score, status, description, submitted_at,
            evaluated_at, duration_seconds, error_message, metrics_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            commit_sha,
            branch,
            score,
            status,
            description,
            submitted_at,
            evaluated_at,
            duration_seconds,
            error_message,
            json.dumps(metrics, sort_keys=True),
        ),
    )


def update_incumbent(conn: sqlite3.Connection, *, commit_sha: str, score: float, promoted_at: str) -> None:
    conn.execute(
        """
        INSERT INTO incumbent (id, commit_sha, score, promoted_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            commit_sha = excluded.commit_sha,
            score = excluded.score,
            promoted_at = excluded.promoted_at
        """,
        (commit_sha, score, promoted_at),
    )


def remote_exists(repo_root: Path, remote_name: str) -> bool:
    output = git(repo_root, "remote", check=False)
    return remote_name in output.splitlines()


def fetch_remote(repo_root: Path, remote_name: str) -> None:
    if not remote_exists(repo_root, remote_name):
        return
    run(["git", "fetch", remote_name], cwd=repo_root, check=False)


def list_proposals(repo_root: Path, *, proposal_prefix: str, remote_name: str) -> list[CandidateRef]:
    refs = ["refs/heads"]
    if remote_exists(repo_root, remote_name):
        refs.append(f"refs/remotes/{remote_name}")
    output = git(
        repo_root,
        "for-each-ref",
        "--format=%(committerdate:unix)\t%(objectname)\t%(refname:short)",
        *refs,
    )
    candidates: list[CandidateRef] = []
    seen: set[tuple[str, str]] = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        timestamp_str, sha, refname = line.split("\t", 2)
        branch = refname[len(remote_name) + 1 :] if refname.startswith(f"{remote_name}/") else refname
        if not branch.startswith(proposal_prefix):
            continue
        key = (branch, sha)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(CandidateRef(sort_key=int(timestamp_str or "0"), refname=refname, branch=branch, sha=sha))
    candidates.sort(key=lambda item: (item.sort_key, item.branch, item.sha))
    return candidates


def commit_subject(repo_root: Path, ref: str) -> str:
    return git(repo_root, "log", "-1", "--format=%s", ref)


def commit_timestamp(repo_root: Path, ref: str) -> str:
    return git(repo_root, "show", "-s", "--format=%cI", ref)


def create_detached_worktree(repo_root: Path, ref: str) -> Path:
    worktree = Path(tempfile.mkdtemp(prefix="autoanything-"))
    git(repo_root, "worktree", "add", "--detach", str(worktree), ref)
    return worktree


def remove_worktree(repo_root: Path, worktree: Path) -> None:
    run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo_root, check=False)


def parse_score_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise ValueError("Score script produced no stdout.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Could not parse score script output as JSON:\n{text}")


def run_score_script(score_script: Path, worktree: Path) -> ScoreResult:
    started = time.time()
    completed = run([str(score_script), str(worktree)], cwd=score_script.parent, check=False)
    duration = time.time() - started
    try:
        payload = parse_score_output(completed.stdout)
    except ValueError as exc:
        message = str(exc)
        if completed.stderr.strip():
            message = f"{message}\n{completed.stderr.strip()}"
        return ScoreResult(ok=False, score=None, metrics={}, error_message=message, duration_seconds=duration)

    score = payload.get("score")
    metrics = payload.get("metrics") or {}
    error_message = payload.get("error")
    ok = completed.returncode == 0 and score is not None and error_message in {None, ""}
    if ok:
        return ScoreResult(ok=True, score=float(score), metrics=metrics, error_message=None, duration_seconds=duration)

    if not error_message:
        error_message = f"Score script exited with status {completed.returncode}."
    if completed.stderr.strip():
        error_message = f"{error_message}\n{completed.stderr.strip()}"
    return ScoreResult(ok=False, score=None, metrics=metrics, error_message=error_message, duration_seconds=duration)


def score_to_text(score: float | None, status: str) -> str:
    if status == "crash" or score is None:
        return "crash"
    return f"{score:.6f}"


def is_better(new_score: float, incumbent_score: float, direction: str) -> bool:
    if direction == "maximize":
        return new_score > incumbent_score
    return new_score < incumbent_score


def export_leaderboard(conn: sqlite3.Connection, leaderboard_path: Path, direction: str) -> None:
    order = "DESC" if direction == "maximize" else "ASC"
    accepted_rows = conn.execute(
        f"""
        SELECT score, branch, description, evaluated_at
        FROM evaluations
        WHERE status IN ('baseline', 'accepted') AND score IS NOT NULL
        ORDER BY score {order}, evaluated_at ASC
        LIMIT 10
        """
    ).fetchall()
    recent_rows = conn.execute(
        """
        SELECT score, status, branch, description, evaluated_at
        FROM evaluations
        ORDER BY evaluated_at DESC, id DESC
        LIMIT 20
        """
    ).fetchall()

    lines = [
        "# Leaderboard",
        "",
        "| # | Score | Branch | Description | When |",
        "|---|-------|--------|-------------|------|",
    ]
    if accepted_rows:
        for index, (score, branch, description, evaluated_at) in enumerate(accepted_rows, start=1):
            when = (evaluated_at or "")[:16].replace("T", " ")
            lines.append(f"| {index} | {float(score):.6f} | {branch} | {description or ''} | {when} |")
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
    if recent_rows:
        for score, status, branch, description, evaluated_at in recent_rows:
            when = (evaluated_at or "")[11:16]
            lines.append(f"| {score_to_text(score, status)} | {status} | {branch} | {description or ''} | {when} |")
    else:
        lines.append("| - | - | - | No evaluations yet | - |")
    leaderboard_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def commit_leaderboard(repo_root: Path, *, base_branch: str, leaderboard_path: Path, branch_label: str) -> bool:
    git(repo_root, "checkout", base_branch)
    relative = leaderboard_path.relative_to(repo_root)
    run(["git", "add", str(relative)], cwd=repo_root, check=True)
    diff_exit = run(["git", "diff", "--cached", "--quiet"], cwd=repo_root, check=False).returncode
    if diff_exit == 0:
        return False
    message = f"chore: update leaderboard after evaluating {branch_label}"
    run(["git", "commit", "-m", message], cwd=repo_root, check=True)
    return True


def push_branch(repo_root: Path, *, remote_name: str, base_branch: str) -> None:
    if not remote_exists(repo_root, remote_name):
        return
    run(["git", "push", remote_name, base_branch], cwd=repo_root, check=False)


def initialize_baseline(
    *,
    repo_root: Path,
    base_branch: str,
    score_script: Path,
    conn: sqlite3.Connection,
    leaderboard_path: Path,
    direction: str,
    remote_name: str,
) -> None:
    git(repo_root, "checkout", base_branch)
    baseline_sha = git(repo_root, "rev-parse", base_branch)
    description = commit_subject(repo_root, baseline_sha)
    submitted_at = commit_timestamp(repo_root, baseline_sha)
    worktree = create_detached_worktree(repo_root, baseline_sha)
    try:
        result = run_score_script(score_script, worktree)
    finally:
        remove_worktree(repo_root, worktree)

    if not result.ok or result.score is None:
        raise RuntimeError(f"Baseline evaluation failed: {result.error_message}")

    evaluated_at = utc_now()
    with conn:
        insert_evaluation(
            conn,
            commit_sha=baseline_sha,
            branch=base_branch,
            score=result.score,
            status="baseline",
            description=description,
            submitted_at=submitted_at,
            evaluated_at=evaluated_at,
            duration_seconds=result.duration_seconds,
            error_message=None,
            metrics=result.metrics,
        )
        update_incumbent(conn, commit_sha=baseline_sha, score=result.score, promoted_at=evaluated_at)
    export_leaderboard(conn, leaderboard_path, direction)
    if commit_leaderboard(repo_root, base_branch=base_branch, leaderboard_path=leaderboard_path, branch_label=base_branch):
        push_branch(repo_root, remote_name=remote_name, base_branch=base_branch)


def merge_candidate(repo_root: Path, *, base_branch: str, refname: str) -> tuple[bool, str | None]:
    git(repo_root, "checkout", base_branch)
    completed = run(["git", "merge", "--no-ff", "--no-edit", refname], cwd=repo_root, check=False)
    if completed.returncode == 0:
        promoted_sha = git(repo_root, "rev-parse", "HEAD")
        return True, promoted_sha
    run(["git", "merge", "--abort"], cwd=repo_root, check=False)
    error = completed.stderr.strip() or completed.stdout.strip() or "git merge failed"
    return False, error


def evaluate_candidate(
    *,
    repo_root: Path,
    candidate: CandidateRef,
    base_branch: str,
    score_script: Path,
    conn: sqlite3.Connection,
    leaderboard_path: Path,
    direction: str,
    remote_name: str,
) -> str:
    incumbent = load_incumbent(conn)
    if incumbent is None:
        raise RuntimeError("No incumbent available. Initialize the baseline first.")
    _, incumbent_score = incumbent

    description = commit_subject(repo_root, candidate.sha)
    submitted_at = commit_timestamp(repo_root, candidate.sha)
    worktree = create_detached_worktree(repo_root, candidate.refname)
    try:
        result = run_score_script(score_script, worktree)
    finally:
        remove_worktree(repo_root, worktree)

    evaluated_at = utc_now()

    if not result.ok or result.score is None:
        with conn:
            insert_evaluation(
                conn,
                commit_sha=candidate.sha,
                branch=candidate.branch,
                score=None,
                status="crash",
                description=description,
                submitted_at=submitted_at,
                evaluated_at=evaluated_at,
                duration_seconds=result.duration_seconds,
                error_message=result.error_message,
                metrics=result.metrics,
            )
        export_leaderboard(conn, leaderboard_path, direction)
        if commit_leaderboard(repo_root, base_branch=base_branch, leaderboard_path=leaderboard_path, branch_label=candidate.branch):
            push_branch(repo_root, remote_name=remote_name, base_branch=base_branch)
        return "crash"

    status = "accepted" if is_better(result.score, incumbent_score, direction) else "rejected"
    promoted_sha: str | None = None
    error_message: str | None = None
    if status == "accepted":
        merged, merge_result = merge_candidate(repo_root, base_branch=base_branch, refname=candidate.refname)
        if not merged:
            status = "crash"
            error_message = f"Proposal scored better but could not be merged cleanly: {merge_result}"
        else:
            promoted_sha = merge_result

    with conn:
        insert_evaluation(
            conn,
            commit_sha=candidate.sha,
            branch=candidate.branch,
            score=result.score,
            status=status,
            description=description,
            submitted_at=submitted_at,
            evaluated_at=evaluated_at,
            duration_seconds=result.duration_seconds,
            error_message=error_message,
            metrics=result.metrics,
        )
        if status == "accepted" and promoted_sha is not None:
            update_incumbent(conn, commit_sha=promoted_sha, score=result.score, promoted_at=evaluated_at)

    export_leaderboard(conn, leaderboard_path, direction)
    if commit_leaderboard(repo_root, base_branch=base_branch, leaderboard_path=leaderboard_path, branch_label=candidate.branch):
        push_branch(repo_root, remote_name=remote_name, base_branch=base_branch)
    return status


def run_evaluation_loop(
    *,
    repo_root: Path,
    base_branch: str,
    proposal_prefix: str,
    direction: str,
    score_script: Path,
    database_path: Path,
    leaderboard_path: Path,
    remote_name: str = "origin",
    once: bool = False,
    sleep_seconds: float = 15.0,
) -> int:
    conn = open_db(database_path)
    try:
        if load_incumbent(conn) is None:
            initialize_baseline(
                repo_root=repo_root,
                base_branch=base_branch,
                score_script=score_script,
                conn=conn,
                leaderboard_path=leaderboard_path,
                direction=direction,
                remote_name=remote_name,
            )

        while True:
            fetch_remote(repo_root, remote_name)
            next_candidate = None
            for candidate in list_proposals(repo_root, proposal_prefix=proposal_prefix, remote_name=remote_name):
                if not already_evaluated(conn, candidate.branch, candidate.sha):
                    next_candidate = candidate
                    break

            if next_candidate is None:
                if once:
                    return 0
                time.sleep(sleep_seconds)
                continue

            evaluate_candidate(
                repo_root=repo_root,
                candidate=next_candidate,
                base_branch=base_branch,
                score_script=score_script,
                conn=conn,
                leaderboard_path=leaderboard_path,
                direction=direction,
                remote_name=remote_name,
            )

            if once:
                return 0
            time.sleep(sleep_seconds)
    finally:
        conn.close()
