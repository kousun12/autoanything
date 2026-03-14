# autoanything

![teaser](progress.png)

AutoAnything generalizes the original autoresearch idea into a reusable framework for black-box optimization with a private evaluator. A challenge repo exposes mutable state, public context, and a public history of attempts. A separate evaluator owns the hidden scoring function, evaluates proposals serially, and promotes only the branches that beat the current incumbent.

This repository ships with:

- a bundled ML training challenge (`state/train.py` + `context/prepare.py`),
- a generic Python toolkit (`autoanything/`) for scaffolding and running challenge repos,
- a GitHub Actions evaluator template,
- a second non-ML example (`examples/prompt-optimizer/`), and
- public artifacts such as `leaderboard.md`, `history/attempts.json`, `dashboard.html`, and `signals.md`.

## Challenge repo layout

```text
problem.yaml             # public problem definition
agent_instructions.md    # public agent protocol
leaderboard.md           # exported evaluation summary
signals.md               # public search guidance
history/attempts.json    # structured attempt history
state/                   # mutable files agents may edit
context/                 # read-only reference files
```

The canonical ML challenge entrypoints are now:

- `state/train.py`
- `context/prepare.py`

Compatibility wrappers remain at the repo root as `train.py` and `prepare.py` so existing workflows do not immediately break.

## Quick start

### 1. Install dependencies

```bash
python3 -m pip install -e .
```

### 2. Prepare the bundled ML challenge data

```bash
python3 prepare.py
```

### 3. Run the bundled ML challenge manually

```bash
python3 train.py
```

### 4. Create the private evaluator scaffolding

```bash
python3 -m autoanything evaluator init   --score-command "uv run state/train.py"   --score-regex '^val_bpb:\s+(?P<value>[-+0-9.eE]+)$'   --ml-metrics
```

This creates a gitignored `evaluator/` directory containing `config.yaml`, `score.sh`, `evaluate_loop.sh`, and eventually `history.db`.

### 5. Evaluate one proposal

```bash
bash evaluator/evaluate_loop.sh --once
```

## CLI overview

### Scaffold a new challenge repo

```bash
python3 -m autoanything init ./my-challenge   --name web-latency   --description "Optimize p99 latency for the demo service"   --mutable state/server.py   --readonly context/load_profile.md   --direction minimize   --score-name p99_ms   --score-description "99th percentile latency in milliseconds"
```

### Scaffold a local evaluator

```bash
python3 -m autoanything evaluator init ./my-challenge   --score-command "python3 state/server.py --benchmark"   --score-regex '^p99_ms:\s+(?P<value>[-+0-9.eE]+)$'
```

## Included examples and documentation

- `docs/problem-owner-guide.md`
- `docs/agent-guide.md`
- `docs/local-evaluator.md`
- `examples/prompt-optimizer/`
- `.github/workflows/evaluate.yml`

## Legacy note

The original `program.md`-driven autoresearch workflow has been superseded by the public challenge protocol in `agent_instructions.md`. The old root entrypoints still exist as thin wrappers for compatibility.

## License

MIT
