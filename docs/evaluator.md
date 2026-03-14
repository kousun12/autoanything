# Evaluator Guide

The evaluator is the private half of an AutoAnything challenge. It owns three responsibilities:

1. score proposals with hidden logic or hidden data
2. compare each result against the current incumbent
3. publish a public `leaderboard.md`

## Local gitignored evaluator

The simplest deployment is a local, gitignored directory inside the challenge repo:

```text
evaluator/
├── score.sh
├── evaluate_loop.sh
├── history.db
└── last_run.log
```

Create it with:

```bash
uv run autoanything evaluator init \
  --repo-root . \
  --direction minimize \
  --base-branch master \
  --score-command "uv run state/train.py" \
  --score-regex "^val_bpb:\\s*([0-9.]+)$"
```

Then edit `evaluator/score.sh` so it reflects your real hidden evaluation procedure.

## Score script contract

`score.sh` receives one argument: the path to a detached worktree containing the proposal.

It should print JSON to stdout:

```json
{"score": 0.9932, "metrics": {"peak_vram_mb": 44123.0}}
```

If evaluation fails, it should exit non-zero and may print:

```json
{"error": "OOM at step 200"}
```

## Evaluate loop behavior

`evaluate_loop.sh` invokes the public evaluator runtime in `src/autoanything/`.

It:

- initializes the baseline if the DB is empty
- scans proposal branches
- evaluates one proposal at a time
- records accepted, rejected, and crash outcomes in SQLite
- exports `leaderboard.md`
- commits the new leaderboard to the base branch

## GitHub Actions deployment

The public workflow in `.github/workflows/evaluate.yml` keeps the orchestration public while leaving
the scoring logic private. The workflow expects a private evaluator repo or private action that can:

- fetch secrets
- run the hidden scorer
- post a PR comment
- merge or close based on the result

The key public requirement is serial evaluation:

```yaml
concurrency:
  group: evaluation
  cancel-in-progress: false
```

## Operational note

Because `leaderboard.md` is committed after each evaluation, proposal branches should periodically
rebase onto the latest base branch to minimize merge friction.
