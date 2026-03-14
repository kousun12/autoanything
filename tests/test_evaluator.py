from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from autoanything.evaluator import LocalEvaluator
from autoanything.scaffold import init_local_evaluator


class EvaluatorFlowTests(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
        return proc.stdout.strip()

    def test_accepts_better_branch_and_rejects_worse_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self.git(repo, "init", "-b", "master")
            self.git(repo, "config", "user.email", "test@example.com")
            self.git(repo, "config", "user.name", "Test User")

            (repo / "state").mkdir()
            (repo / "context").mkdir()
            (repo / "history").mkdir()
            (repo / "state" / "value.txt").write_text("10\n")
            (repo / "context" / "notes.txt").write_text("read only\n")
            (repo / "score_candidate.py").write_text(
                "from pathlib import Path\n"
                "value = float((Path('state') / 'value.txt').read_text().strip())\n"
                "print(f'score: {value:.1f}')\n"
            )
            (repo / "problem.yaml").write_text(
                "name: demo\n"
                "description: Demo evaluator flow\n"
                "mutable:\n"
                "  - state/value.txt\n"
                "readonly:\n"
                "  - context/notes.txt\n"
                "score:\n"
                "  direction: minimize\n"
                "  name: score\n"
                "  description: lower is better\n"
                "  bounded: false\n"
                "constraints:\n"
                "  - Only edit state/value.txt\n"
            )
            (repo / "leaderboard.md").write_text("# Leaderboard\n")
            (repo / "signals.md").write_text("# Search Signals\n")
            (repo / "signals.json").write_text("{}\n")
            (repo / "dashboard.html").write_text("<html></html>\n")
            (repo / "history" / "attempts.json").write_text("[]\n")

            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "baseline")

            self.git(repo, "checkout", "-b", "proposals/alice/better")
            (repo / "state" / "value.txt").write_text("8\n")
            self.git(repo, "commit", "-am", "make score better")
            self.git(repo, "checkout", "master")

            self.git(repo, "checkout", "-b", "proposals/bob/worse")
            (repo / "state" / "value.txt").write_text("12\n")
            self.git(repo, "commit", "-am", "make score worse")
            self.git(repo, "checkout", "master")

            init_local_evaluator(
                repo,
                score_command="python3 score_candidate.py",
                score_regex=r"^score:\s+(?P<value>[-+0-9.eE]+)$",
                stale_after_base_commits=None,
                fetch_remote=False,
                commit_public_artifacts=False,
                push_after_update=False,
            )

            evaluator = LocalEvaluator(repo / "evaluator" / "config.yaml")
            evaluator.ensure_baseline()
            first = evaluator.evaluate_once()
            second = evaluator.evaluate_once()

            self.assertEqual(first["status"], "accepted")
            self.assertEqual(second["status"], "rejected")
            self.assertEqual(self.git(repo, "show", "master:state/value.txt"), "8")
            leaderboard = (repo / "leaderboard.md").read_text()
            self.assertIn("proposals/alice/better", leaderboard)
            self.assertIn("proposals/bob/worse", leaderboard)
            history = (repo / "history" / "attempts.json").read_text()
            self.assertIn('"status": "accepted"', history)
            self.assertIn('"status": "rejected"', history)


if __name__ == "__main__":
    unittest.main()
