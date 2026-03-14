from __future__ import annotations

import stat
import textwrap
from pathlib import Path


def prompt_if_missing(value: str | None, message: str) -> str:
    if value:
        return value
    return input(f"{message}: ").strip()


def bool_from_flag(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError(f"Could not parse boolean value: {value!r}")


def write_text(path: Path, content: str, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists. Use --overwrite to replace it.")
    path.write_text(content, encoding="utf-8")


def make_executable(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_gitignore_entry(repo_root: Path, entry: str) -> None:
    gitignore_path = repo_root / ".gitignore"
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        lines = content.splitlines()
    else:
        content = ""
        lines = []
    if entry in lines:
        return
    suffix = "\n" if content and not content.endswith("\n") else ""
    gitignore_path.write_text(f"{content}{suffix}{entry}\n", encoding="utf-8")


def _yaml_block(value: str, *, indent: int = 2) -> str:
    stripped = value.strip()
    if not stripped:
        return '""'
    wrapped = textwrap.indent(stripped, " " * indent)
    return f"|\n{wrapped}"


def render_problem_yaml(
    *,
    name: str,
    description: str,
    mutable: list[str],
    readonly: list[str],
    score_direction: str,
    score_name: str,
    score_description: str,
    bounded: bool,
    bound: float | None,
    constraints: list[str],
) -> str:
    mutable_lines = "\n".join(f"  - {item}" for item in mutable) or "  []"
    readonly_lines = "\n".join(f"  - {item}" for item in readonly) or "  []"
    constraints_lines = "\n".join(f'  - "{item}"' for item in constraints) or '  - "None declared yet"'
    bound_line = f"\n  bound: {bound}" if bounded and bound is not None else ""
    return textwrap.dedent(
        f"""\
        name: {name}
        description: {_yaml_block(description)}

        mutable:
        {mutable_lines}

        readonly:
        {readonly_lines}

        score:
          direction: {score_direction}
          name: {score_name}
          description: "{score_description}"
          bounded: {"true" if bounded else "false"}{bound_line}

        constraints:
        {constraints_lines}
        """
    )


def render_agent_instructions(*, base_branch: str, problem_file: str = "problem.yaml") -> str:
    return textwrap.dedent(
        f"""\
        # How to Participate

        1. Pull the latest `{base_branch}` and create a proposal branch named `proposals/<your-name>/<short-description>`.
        2. Read `{problem_file}` to understand the objective, score direction, and file boundaries.
        3. Read the files listed under `readonly` for background context.
        4. Read `leaderboard.md` to see what has already worked, failed, or crashed.
        5. Modify only the files listed under `mutable` in `{problem_file}`.
        6. Commit with a clear message describing the idea you tried.
        7. Push your branch.

        The evaluator runs privately. Agents do not get to see the scoring code or hidden test data.
        Each proposal is evaluated serially against the current incumbent. If it improves the score it
        is merged forward; otherwise it is recorded on the leaderboard and discarded.
        """
    )


def render_leaderboard() -> str:
    return textwrap.dedent(
        """\
        # Leaderboard

        _No evaluations have been published yet._

        | # | Score | Branch | Description | When |
        |---|-------|--------|-------------|------|

        ## Recent Attempts

        | Score | Status | Branch | Description | When |
        |-------|--------|--------|-------------|------|
        """
    )


def render_context_readme() -> str:
    return textwrap.dedent(
        """\
        # Context

        Files in this directory are public, read-only reference material for agents.
        They provide the background needed to propose changes, but they are not part of
        the mutable search space.
        """
    )


def render_mutable_placeholder() -> str:
    return textwrap.dedent(
        """\
        # Mutable State

        Replace this file with the artifact agents are allowed to improve.
        """
    )


def render_score_script(score_command: str, score_regex: str) -> str:
    escaped_regex = score_regex.replace("\\", "\\\\").replace('"', '\\"')
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail

        WORKTREE="${{1:?usage: score.sh <worktree>}}"
        SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
        LOG_FILE="$SCRIPT_DIR/last_run.log"
        RESULT_FILE="$SCRIPT_DIR/last_result.json"

        cd "$WORKTREE"
        if {score_command} >"$LOG_FILE" 2>&1; then
          STATUS=0
        else
          STATUS=$?
        fi

        python - "$LOG_FILE" "$RESULT_FILE" "$STATUS" <<'PY'
        import json
        import pathlib
        import re
        import sys

        log_path = pathlib.Path(sys.argv[1])
        result_path = pathlib.Path(sys.argv[2])
        exit_status = int(sys.argv[3])
        text = log_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"{escaped_regex}", text, re.MULTILINE)

        if exit_status == 0 and match:
            payload = {{
                "score": float(match.group(1)),
                "metrics": {{}},
            }}
            result_path.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
            print(json.dumps(payload))
            raise SystemExit(0)

        payload = {{
            "error": f"Scoring command failed with exit status {{exit_status}} or score regex did not match.",
            "metrics": {{}},
        }}
        result_path.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
        print(json.dumps(payload))
        raise SystemExit(1)
        PY
        """
    )


def render_evaluator_readme() -> str:
    return textwrap.dedent(
        """\
        # Private Evaluator

        This directory is intentionally gitignored. Customize `score.sh` so it runs your
        real evaluation command and emits JSON with a top-level `score` field. The public
        repo only sees `leaderboard.md`; it never sees the hidden scoring code or data.

        Useful commands:

        - `bash evaluator/evaluate_loop.sh --once` to process one queued proposal
        - `bash evaluator/evaluate_loop.sh` to run the serial loop continuously
        """
    )


def render_evaluate_loop(
    *,
    repo_root: Path,
    base_branch: str,
    proposal_prefix: str,
    direction: str,
    leaderboard_path: str,
) -> str:
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail

        SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
        REPO_ROOT="{repo_root.resolve()}"

        exec uv run python -m autoanything internal-evaluate \\
          --repo-root "$REPO_ROOT" \\
          --base-branch "{base_branch}" \\
          --proposal-prefix "{proposal_prefix}" \\
          --direction "{direction}" \\
          --score-script "$SCRIPT_DIR/score.sh" \\
          --database "$SCRIPT_DIR/history.db" \\
          --leaderboard "$REPO_ROOT/{leaderboard_path}" \\
          "$@"
        """
    )


def init_challenge(
    *,
    target_path: Path,
    name: str,
    description: str,
    mutable: list[str],
    readonly: list[str],
    score_direction: str,
    score_name: str,
    score_description: str,
    bounded: bool,
    bound: float | None,
    constraints: list[str],
    base_branch: str,
    overwrite: bool,
) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    write_text(
        target_path / "problem.yaml",
        render_problem_yaml(
            name=name,
            description=description,
            mutable=mutable,
            readonly=readonly,
            score_direction=score_direction,
            score_name=score_name,
            score_description=score_description,
            bounded=bounded,
            bound=bound,
            constraints=constraints,
        ),
        overwrite=overwrite,
    )
    write_text(target_path / "agent_instructions.md", render_agent_instructions(base_branch=base_branch), overwrite=overwrite)
    write_text(target_path / "leaderboard.md", render_leaderboard(), overwrite=overwrite)
    write_text(target_path / "context" / "README.md", render_context_readme(), overwrite=overwrite)
    write_text(target_path / "state" / "README.md", render_mutable_placeholder(), overwrite=overwrite)
    ensure_gitignore_entry(target_path, "evaluator/")


def init_evaluator(
    *,
    repo_root: Path,
    score_command: str,
    score_regex: str,
    direction: str,
    base_branch: str,
    proposal_prefix: str,
    leaderboard_path: str,
    overwrite: bool,
) -> None:
    evaluator_dir = repo_root / "evaluator"
    evaluator_dir.mkdir(parents=True, exist_ok=True)
    ensure_gitignore_entry(repo_root, "evaluator/")

    score_script = evaluator_dir / "score.sh"
    write_text(score_script, render_score_script(score_command, score_regex), overwrite=overwrite)
    make_executable(score_script)

    loop_script = evaluator_dir / "evaluate_loop.sh"
    write_text(
        loop_script,
        render_evaluate_loop(
            repo_root=repo_root,
            base_branch=base_branch,
            proposal_prefix=proposal_prefix,
            direction=direction,
            leaderboard_path=leaderboard_path,
        ),
        overwrite=overwrite,
    )
    make_executable(loop_script)
    write_text(evaluator_dir / "README.md", render_evaluator_readme(), overwrite=overwrite)


def build_challenge_from_args(args) -> None:
    target_path = Path(prompt_if_missing(args.path, "Challenge path")).resolve()
    name = prompt_if_missing(args.name, "Challenge name")
    description = prompt_if_missing(args.description, "Challenge description")
    score_name = prompt_if_missing(args.score_name, "Score name")
    score_description = prompt_if_missing(args.score_description, "Score description")
    mutable = args.mutable or ["state/your_mutable_file.txt"]
    readonly = args.readonly or ["context/README.md"]
    constraints = args.constraint or []
    init_challenge(
        target_path=target_path,
        name=name,
        description=description,
        mutable=mutable,
        readonly=readonly,
        score_direction=args.score_direction,
        score_name=score_name,
        score_description=score_description,
        bounded=bool_from_flag(args.bounded, default=False),
        bound=args.score_bound,
        constraints=constraints,
        base_branch=args.base_branch,
        overwrite=args.overwrite,
    )


def build_evaluator_from_args(args) -> None:
    repo_root = Path(args.repo_root).resolve()
    score_command = prompt_if_missing(args.score_command, "Score command to run inside the worktree")
    score_regex = prompt_if_missing(
        args.score_regex,
        "Regex with one capture group for the numeric score (example: ^val_bpb:\\s*([0-9.]+)$)",
    )
    init_evaluator(
        repo_root=repo_root,
        score_command=score_command,
        score_regex=score_regex,
        direction=args.direction,
        base_branch=args.base_branch,
        proposal_prefix=args.proposal_prefix,
        leaderboard_path=args.leaderboard,
        overwrite=args.overwrite,
    )
