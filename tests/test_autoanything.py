from __future__ import annotations

import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoanything.evaluator import run_evaluation_loop
from autoanything.scaffold import init_challenge, init_evaluator


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


class AutoAnythingScaffoldTests(unittest.TestCase):
    def test_init_challenge_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            challenge = Path(tmpdir) / "challenge"
            init_challenge(
                target_path=challenge,
                name="demo-problem",
                description="Optimize a simple numeric score.",
                mutable=["state/score.txt"],
                readonly=["context/rules.md"],
                score_direction="maximize",
                score_name="score",
                score_description="A simple maximization target",
                bounded=True,
                bound=100.0,
                constraints=["Do not touch hidden data"],
                base_branch="master",
                overwrite=False,
            )

            problem = (challenge / "problem.yaml").read_text(encoding="utf-8")
            self.assertIn("name: demo-problem", problem)
            self.assertIn("  - state/score.txt", problem)
            self.assertIn("direction: maximize", problem)
            self.assertIn("bounded: true", problem)
            self.assertIn("bound: 100.0", problem)
            self.assertTrue((challenge / "agent_instructions.md").exists())
            self.assertTrue((challenge / "leaderboard.md").exists())
            self.assertTrue((challenge / ".gitignore").exists())

    def test_init_evaluator_creates_private_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            init_evaluator(
                repo_root=repo,
                score_command='printf "score: 1.0\\n"',
                score_regex=r"^score:\s*([0-9.]+)$",
                direction="maximize",
                base_branch="master",
                proposal_prefix="proposals/",
                leaderboard_path="leaderboard.md",
                overwrite=False,
            )
            score_script = repo / "evaluator" / "score.sh"
            loop_script = repo / "evaluator" / "evaluate_loop.sh"
            self.assertTrue(score_script.exists())
            self.assertTrue(loop_script.exists())
            self.assertTrue(score_script.stat().st_mode & stat.S_IXUSR)
            self.assertTrue(loop_script.stat().st_mode & stat.S_IXUSR)


class AutoAnythingEvaluatorIntegrationTests(unittest.TestCase):
    def test_evaluator_accepts_better_branch_and_rejects_worse_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            init_challenge(
                target_path=repo,
                name="score-problem",
                description="Maximize the integer written in state/score.txt.",
                mutable=["state/score.txt"],
                readonly=["context/rules.md"],
                score_direction="maximize",
                score_name="score",
                score_description="Integer score",
                bounded=False,
                bound=None,
                constraints=["Only edit the mutable file"],
                base_branch="master",
                overwrite=False,
            )
            (repo / "state" / "score.txt").write_text("10\n", encoding="utf-8")
            (repo / "context" / "rules.md").write_text("Higher is better.\n", encoding="utf-8")

            git(repo, "init", "-b", "master")
            git(repo, "config", "user.name", "AutoAnything Test")
            git(repo, "config", "user.email", "autoanything@example.com")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "initial baseline")

            evaluator_dir = repo / "evaluator"
            evaluator_dir.mkdir()
            score_script = evaluator_dir / "score.sh"
            score_script.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
WORKTREE="${1:?usage: score.sh <worktree>}"
python3 - "$WORKTREE" <<'PY'
import json
import pathlib
import sys

worktree = pathlib.Path(sys.argv[1])
score = float((worktree / "state" / "score.txt").read_text(encoding="utf-8").strip())
print(json.dumps({"score": score, "metrics": {"source": "test"}}))
PY
""",
                encoding="utf-8",
            )
            score_script.chmod(score_script.stat().st_mode | stat.S_IXUSR)

            leaderboard_path = repo / "leaderboard.md"
            database_path = evaluator_dir / "history.db"

            run_evaluation_loop(
                repo_root=repo,
                base_branch="master",
                proposal_prefix="proposals/",
                direction="maximize",
                score_script=score_script,
                database_path=database_path,
                leaderboard_path=leaderboard_path,
                once=True,
                remote_name="origin",
            )

            git(repo, "checkout", "-b", "proposals/alice/better")
            (repo / "state" / "score.txt").write_text("20\n", encoding="utf-8")
            git(repo, "add", "state/score.txt")
            git(repo, "commit", "-m", "raise score to 20")
            git(repo, "checkout", "master")

            run_evaluation_loop(
                repo_root=repo,
                base_branch="master",
                proposal_prefix="proposals/",
                direction="maximize",
                score_script=score_script,
                database_path=database_path,
                leaderboard_path=leaderboard_path,
                once=True,
                remote_name="origin",
            )

            self.assertEqual(git(repo, "show", "master:state/score.txt"), "20")

            git(repo, "checkout", "-b", "proposals/bob/worse", "master")
            (repo / "state" / "score.txt").write_text("5\n", encoding="utf-8")
            git(repo, "add", "state/score.txt")
            git(repo, "commit", "-m", "drop score to 5")
            git(repo, "checkout", "master")

            run_evaluation_loop(
                repo_root=repo,
                base_branch="master",
                proposal_prefix="proposals/",
                direction="maximize",
                score_script=score_script,
                database_path=database_path,
                leaderboard_path=leaderboard_path,
                once=True,
                remote_name="origin",
            )

            self.assertEqual(git(repo, "show", "master:state/score.txt"), "20")
            leaderboard = leaderboard_path.read_text(encoding="utf-8")
            self.assertIn("proposals/alice/better", leaderboard)
            self.assertIn("accepted", leaderboard)
            self.assertIn("proposals/bob/worse", leaderboard)
            self.assertIn("rejected", leaderboard)


if __name__ == "__main__":
    unittest.main()
