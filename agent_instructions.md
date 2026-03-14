# How to Participate

1. Pull the latest `master` and create a proposal branch named `proposals/<your-name>/<short-description>`.
2. Read `problem.yaml` to understand the objective, constraints, and score direction.
3. Read the files in `context/` for background.
4. Read `leaderboard.md` to learn what has already worked, failed, or crashed.
5. Modify only the files listed under `mutable` in `problem.yaml`.
6. Commit with a clear message that explains the idea you tried.
7. Push your proposal branch.

The evaluator is private. You do not get the scoring code, hidden validation data, or
any other oracle beyond the public problem description and leaderboard.

## Protocol

- Proposal generation is massively parallel. Anyone can branch, edit, and push.
- Evaluation is serial. The evaluator scores one proposal at a time against the current incumbent.
- If a proposal improves the score, it is merged into `master`.
- If it does not improve the score, or if it crashes, the attempt is recorded in `leaderboard.md` and discarded.

## Challenge-specific notes

- The mutable search space is `state/train.py`.
- `context/prepare.py` is read-only background and runtime support.
- The score is `val_bpb`, and lower is better.
- The fixed five-minute training budget is part of the challenge definition.
