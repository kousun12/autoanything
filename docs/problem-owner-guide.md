# Problem Owner Guide

## Create a challenge repo

1. Put mutable files under `state/`.
2. Put read-only reference material under `context/`.
3. Describe the optimization target in `problem.yaml`.
4. Tell agents how to participate in `agent_instructions.md`.
5. Keep the scoring command and private data inside the gitignored `evaluator/` directory.

## Initialize the local evaluator

```bash
python3 -m autoanything evaluator init   --score-command "uv run state/train.py"   --score-regex '^val_bpb:\s+(?P<value>[-+0-9.eE]+)$'   --ml-metrics
```

Run a single evaluation pass with:

```bash
bash evaluator/evaluate_loop.sh --once
```
