from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autoanything.models import ProblemDefinition, ScoreDefinition
from autoanything.scaffold import init_challenge, init_local_evaluator


class ScaffoldTests(unittest.TestCase):
    def test_init_challenge_and_evaluator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            problem = ProblemDefinition(
                name="demo",
                description="Demo challenge",
                mutable=["state/value.txt"],
                readonly=["context/readme.txt"],
                score=ScoreDefinition(direction="minimize", name="score", description="lower is better"),
                constraints=["Only edit state/value.txt"],
            )
            init_challenge(repo, problem)
            self.assertTrue((repo / "problem.yaml").exists())
            self.assertTrue((repo / "leaderboard.md").exists())
            self.assertTrue((repo / "history" / "attempts.json").exists())

            init_local_evaluator(
                repo,
                score_command="python3 score.py",
                score_regex=r"^score:\s+(?P<value>[-+0-9.eE]+)$",
                fetch_remote=False,
                commit_public_artifacts=False,
                push_after_update=False,
            )
            self.assertTrue((repo / "evaluator" / "config.yaml").exists())
            self.assertIn("evaluator/", (repo / ".gitignore").read_text())


if __name__ == "__main__":
    unittest.main()
