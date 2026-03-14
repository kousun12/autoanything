from __future__ import annotations

from pathlib import Path

from .models import EvaluatorConfig, MetricPattern, ProblemDefinition, dump_yaml


def _write(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if executable:
        path.chmod(0o755)


def ensure_gitignore_entry(repo_root: Path, entry: str) -> None:
    gitignore_path = repo_root / ".gitignore"
    if gitignore_path.exists():
        lines = gitignore_path.read_text().splitlines()
    else:
        lines = []
    if entry not in lines:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(entry)
        gitignore_path.write_text("\n".join(lines) + "\n")


def init_challenge(
    repo_root: Path,
    problem: ProblemDefinition,
    *,
    overwrite: bool = False,
    include_strategy_templates: bool = True,
) -> None:
    repo_root = repo_root.resolve()
    for rel_path in problem.mutable + problem.readonly:
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)

    if overwrite or not (repo_root / "problem.yaml").exists():
        _write(repo_root / "problem.yaml", dump_yaml(problem.to_dict()))

    if overwrite or not (repo_root / "leaderboard.md").exists():
        _write(
            repo_root / "leaderboard.md",
            "# Leaderboard\n\nNo evaluations have been recorded yet.\n\n## Recent Attempts\n\nNo attempts have been recorded yet.\n",
        )

    if overwrite or not (repo_root / "agent_instructions.md").exists():
        _write(
            repo_root / "agent_instructions.md",
            "# How to Participate\n\n"
            "1. Read `problem.yaml`.\n"
            "2. Review `leaderboard.md`, `signals.md`, and `history/attempts.json`.\n"
            "3. Create a branch named `proposals/<agent>/<idea>`.\n"
            "4. Edit only the mutable files listed in the problem definition.\n"
            "5. Commit with a clear explanation and push the branch.\n",
        )

    if include_strategy_templates:
        strategy_dir = repo_root / "strategies"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        templates = {
            "conservative.md": "# Conservative Strategy\n\nPrefer low-risk changes with clear reasoning.\n",
            "radical.md": "# Radical Strategy\n\nTry a bold change when the search appears stuck.\n",
            "specialist.md": "# Specialist Strategy\n\nFocus on one subsystem and tune it deeply.\n",
            "crossover.md": "# Crossover Strategy\n\nImport an idea from a neighboring domain.\n",
        }
        for filename, content in templates.items():
            target = strategy_dir / filename
            if overwrite or not target.exists():
                _write(target, content)

    if overwrite or not (repo_root / "history" / "attempts.json").exists():
        _write(repo_root / "history" / "attempts.json", "[]\n")
    if overwrite or not (repo_root / "signals.md").exists():
        _write(repo_root / "signals.md", "# Search Signals\n\nNo evaluator signals have been published yet.\n")
    if overwrite or not (repo_root / "signals.json").exists():
        _write(repo_root / "signals.json", '{\n  "recent_failures": 0,\n  "status": "cold-start",\n  "message": "No evaluator signals have been published yet."\n}\n')
    if overwrite or not (repo_root / "dashboard.html").exists():
        _write(repo_root / "dashboard.html", "<!doctype html><html><body><h1>AutoAnything Dashboard</h1><p>No evaluations yet.</p></body></html>\n")


def default_ml_metrics() -> list[MetricPattern]:
    return [
        MetricPattern("training_seconds", r"^training_seconds:\s+(?P<value>[-+0-9.eE]+)$"),
        MetricPattern("total_seconds", r"^total_seconds:\s+(?P<value>[-+0-9.eE]+)$"),
        MetricPattern("peak_vram_mb", r"^peak_vram_mb:\s+(?P<value>[-+0-9.eE]+)$"),
        MetricPattern("mfu_percent", r"^mfu_percent:\s+(?P<value>[-+0-9.eE]+)$"),
        MetricPattern("total_tokens_M", r"^total_tokens_M:\s+(?P<value>[-+0-9.eE]+)$"),
        MetricPattern("num_steps", r"^num_steps:\s+(?P<value>[-+0-9.eE]+)$"),
        MetricPattern("num_params_M", r"^num_params_M:\s+(?P<value>[-+0-9.eE]+)$"),
        MetricPattern("depth", r"^depth:\s+(?P<value>[-+0-9.eE]+)$"),
    ]


def init_local_evaluator(
    repo_root: Path,
    *,
    score_command: str,
    score_regex: str,
    metrics: list[MetricPattern] | None = None,
    base_branch: str = "master",
    proposal_prefixes: list[str] | None = None,
    queue_policy: str = "fifo",
    stale_after_base_commits: int | None = 20,
    fetch_remote: bool = True,
    commit_public_artifacts: bool = True,
    push_after_update: bool = True,
    overwrite: bool = False,
) -> EvaluatorConfig:
    repo_root = repo_root.resolve()
    evaluator_dir = repo_root / "evaluator"
    evaluator_dir.mkdir(parents=True, exist_ok=True)
    ensure_gitignore_entry(repo_root, "evaluator/")

    config = EvaluatorConfig(
        config_path=(evaluator_dir / "config.yaml").resolve(),
        repo_root=repo_root,
        problem_path=(repo_root / "problem.yaml").resolve(),
        db_path=(evaluator_dir / "history.db").resolve(),
        base_branch=base_branch,
        proposal_prefixes=proposal_prefixes or ["proposals/"],
        queue_policy=queue_policy,
        stale_after_base_commits=stale_after_base_commits,
        fetch_remote=fetch_remote,
        commit_public_artifacts=commit_public_artifacts,
        push_after_update=push_after_update,
        score_command=score_command,
        score_regex=score_regex,
        metrics=metrics or [],
        private_log_path=(evaluator_dir / "last-score.log").resolve(),
        result_path=(evaluator_dir / "result.json").resolve(),
        leaderboard_path=(repo_root / "leaderboard.md").resolve(),
        history_json_path=(repo_root / "history" / "attempts.json").resolve(),
        dashboard_path=(repo_root / "dashboard.html").resolve(),
        signals_markdown_path=(repo_root / "signals.md").resolve(),
        signals_json_path=(repo_root / "signals.json").resolve(),
    )

    if overwrite or not (evaluator_dir / "config.yaml").exists():
        _write(evaluator_dir / "config.yaml", dump_yaml(config.to_dict()))
    if overwrite or not (evaluator_dir / "score.sh").exists():
        _write(
            evaluator_dir / "score.sh",
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "ROOT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/..\" && pwd)\"\n"
            "cd \"$ROOT_DIR\"\n"
            "python3 -m autoanything evaluator score --config \"$ROOT_DIR/evaluator/config.yaml\" \"$@\"\n",
            executable=True,
        )
    if overwrite or not (evaluator_dir / "evaluate_loop.sh").exists():
        _write(
            evaluator_dir / "evaluate_loop.sh",
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "ROOT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/..\" && pwd)\"\n"
            "cd \"$ROOT_DIR\"\n"
            "python3 -m autoanything evaluator loop --config \"$ROOT_DIR/evaluator/config.yaml\" \"$@\"\n",
            executable=True,
        )
    if overwrite or not (evaluator_dir / "README.md").exists():
        _write(
            evaluator_dir / "README.md",
            "# Private evaluator\n\n"
            "This directory is intentionally gitignored. It contains the scoring command, the SQLite history database, and any private test assets needed to evaluate proposals.\n",
        )

    return config
