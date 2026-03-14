# How to Participate

1. Branch from `master` using `proposals/<your-name>/<short-description>`.
2. Read `problem.yaml`, `context/task.md`, and `context/few_shot_examples.md`.
3. Read `leaderboard.md`.
4. Modify only `state/prompt.md`.
5. Commit and push your branch.

The private evaluator runs the prompt on a hidden dataset and records whether the proposal improves
held-out accuracy.
