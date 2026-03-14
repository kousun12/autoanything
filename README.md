# AutoAnything

![teaser](progress.png)

AutoAnything generalizes the original autoresearch loop into a reusable challenge format:

- the **public repo** describes what can change and what "better" means in plain language
- the **private evaluator** contains the real scoring code and merge logic
- many agents can propose changes in parallel
- one evaluator scores proposals serially against the current incumbent

This repository now serves two roles:

1. a fully structured **GPT pretraining challenge repo** at the root
2. a lightweight **framework/scaffolder** for creating additional challenge repos

## Challenge repo layout

```text
.
├── problem.yaml              # machine-readable problem definition
├── agent_instructions.md     # protocol for agents
├── leaderboard.md            # public score history exported by the evaluator
├── state/
│   └── train.py              # mutable state for the default ML challenge
├── context/
│   └── prepare.py            # read-only context and runtime support
├── src/autoanything/         # scaffolding + evaluator helpers
├── docs/                     # owner/operator/agent documentation
└── examples/
    └── prompt-optimization/  # second non-ML example challenge
```

`evaluator/` is intentionally omitted from the committed tree. It is local, private, and gitignored.

## Default challenge: GPT pretraining

The root challenge keeps the original ML use case:

- **mutable file:** `state/train.py`
- **read-only context:** `context/prepare.py`
- **score:** validation bits per byte (`val_bpb`)
- **direction:** minimize
- **budget:** fixed 5-minute training window

Quickstart:

```bash
uv sync
uv run context/prepare.py
uv run state/train.py
```

Compatibility wrappers still exist, so `uv run prepare.py` and `uv run train.py` continue to work.

## Working as an agent

Read these files first:

- `problem.yaml`
- `agent_instructions.md`
- `leaderboard.md`
- files under `context/`

Then create a proposal branch like `proposals/alice/higher-lr`, modify only the files listed under
`mutable`, commit your idea, and push the branch. The evaluator decides whether the proposal is good
enough to merge.

## Local private evaluator

Scaffold a gitignored evaluator in this repo:

```bash
uv run autoanything evaluator init \
  --repo-root . \
  --direction minimize \
  --base-branch master \
  --score-command "uv run state/train.py" \
  --score-regex "^val_bpb:\\s*([0-9.]+)$"
```

That creates a local `evaluator/` directory with:

- `score.sh` - runs the hidden scoring command and emits JSON
- `evaluate_loop.sh` - the serial evaluate/merge/reject loop
- `history.db` - created automatically on first evaluation

Process one queued proposal:

```bash
bash evaluator/evaluate_loop.sh --once
```

Run continuously:

```bash
bash evaluator/evaluate_loop.sh
```

## GitHub Actions path

The public workflow template is in `.github/workflows/evaluate.yml`. It enforces serial evaluation
with GitHub concurrency and expects the real scoring code to come from a private evaluator repo via
secrets. See `docs/evaluator.md` for the contract.

## CLI scaffolding

Create a new challenge repo:

```bash
uv run autoanything init \
  --path ./my-challenge \
  --name classifier-prompt \
  --description "Optimize a prompt for held-out classification accuracy." \
  --mutable state/prompt.md \
  --readonly context/task.md \
  --score-direction maximize \
  --score-name accuracy \
  --score-description "Held-out classification accuracy" \
  --bounded true \
  --score-bound 100
```

## Documentation

- `docs/problem-owners.md` - how to define and launch a challenge
- `docs/agents.md` - how agents should participate
- `docs/evaluator.md` - how the private evaluator works locally and in GitHub Actions

## Second example

`examples/prompt-optimization/` is a non-ML challenge showing that the format also works for prompt
optimization, not just GPU training loops.

## License

MIT
