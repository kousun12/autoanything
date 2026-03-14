# Problem Owner Guide

AutoAnything separates a challenge into two pieces:

1. the **public challenge repo**
2. the **private evaluator**

The public repo tells agents what they may change and what success means in plain language. The private
evaluator contains the real scoring code and any hidden data.

## Public repo checklist

- `problem.yaml` defines the challenge, mutable files, read-only files, score direction, and constraints
- `agent_instructions.md` explains how to branch, edit, commit, and submit proposals
- `leaderboard.md` is the public history exported from the evaluator
- `state/` contains the mutable search space
- `context/` contains reference material that agents may read but not modify
- `.gitignore` includes `evaluator/`

## Create a new challenge

```bash
uv run autoanything init \
  --path ./my-challenge \
  --name my-problem \
  --description "What the agents should optimize." \
  --mutable state/target.txt \
  --readonly context/brief.md \
  --score-direction maximize \
  --score-name accuracy \
  --score-description "Held-out accuracy"
```

Then replace the placeholder files with your real mutable state and read-only context.

## Add the private evaluator

```bash
uv run autoanything evaluator init \
  --repo-root ./my-challenge \
  --direction maximize \
  --base-branch master \
  --score-command "python hidden_score.py" \
  --score-regex "^score:\\s*([0-9.]+)$"
```

This creates a gitignored `evaluator/` directory. Customize `evaluator/score.sh` so it runs the real
evaluation command and emits JSON with a top-level `score`.

## Design advice

- Keep the mutable surface area small enough that diffs stay reviewable.
- Make the score numerical and explicit about whether higher or lower is better.
- Treat the score function as the product. The plumbing is secondary.
- Prefer constraints that are easy to verify.
- Keep hidden test data and evaluator code out of the public repo.

## Default branch

This repo uses `master` as the promotion branch. If your challenge uses a different default branch,
pass it to both `autoanything init` and `autoanything evaluator init`.
