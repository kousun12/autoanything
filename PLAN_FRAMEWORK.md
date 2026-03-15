# Plan: AutoAnything as an Installable Framework

## The Problem

AutoAnything is currently a **repo you fork**. To use it, you clone the whole thing, run `activate.sh` to copy problem files into the repo root, and run evaluator scripts from hardcoded paths. This works for developing the framework itself, but it doesn't scale to the vision: many people, many problems, a population of agents submitting solutions.

The pain points:

1. **Single problem at a time.** `activate.sh` overwrites the repo root — you can't work on two problems simultaneously.
2. **Framework and problem are entangled.** The evaluator code, test problems, and active problem all live in one repo. Users have to understand the framework internals to use it.
3. **No upgrade path.** If the evaluator improves, every user has to manually pull changes into their fork.
4. **Fragile configuration.** `problem.yaml` is parsed with string matching (no YAML library). The metric name defaults to `val_bpb` if parsing fails silently. Branch name `master` and path `proposals/*` are hardcoded constants.
5. **Monolithic dependencies.** GPU-heavy deps (torch, tiktoken) sit alongside instant-scoring problems in one `pyproject.toml`.
6. **No onboarding story.** There's no `init` command, no scaffolding. A new user reads the README, studies the test problems, and assembles their problem by hand.

## The Proposal

Transform AutoAnything from a template repository into an **installable CLI tool**. Problems become self-contained directories (or repos). The framework provides the evaluator runtime, and problems provide the scoring function and mutable state.

```
pip install autoanything       # or: uv tool install autoanything

autoanything init my-problem   # scaffold a new problem
cd my-problem
# ... set up scoring, state, context ...
autoanything score             # run score.sh once (sanity check)
autoanything evaluate          # start polling evaluator
autoanything serve             # start webhook server
```

This is the same evolution that happened with Jekyll (you install it, then create a site), pytest (you install it, then it discovers tests), and Cargo (you install it, then create a project). The common pattern: separate the runtime from the content it operates on.

## What a Problem Looks Like

A problem is a directory with a fixed structure. It can be its own git repo (the typical case — agents clone it and push branches) or a subdirectory of a larger project.

```
my-problem/
├── problem.yaml            # problem definition + framework config
├── agent_instructions.md   # protocol for agents (can be generated)
├── state/                  # mutable files agents edit
│   └── solution.py
├── context/                # read-only background for agents
│   └── background.py
├── scoring/                # GITIGNORED — private scoring code
│   └── score.sh            # outputs JSON on last line
├── leaderboard.md          # auto-updated by the evaluator
└── .autoanything/          # GITIGNORED — local evaluator state
    └── history.db          # SQLite evaluation history
```

This is almost identical to the current structure. The differences:

- `scoring/` replaces `evaluator/score.sh` as the conventional location for private scoring code. The name is clearer — "scoring" is what it does, "evaluator" is the tool that runs it.
- `.autoanything/` holds evaluator state (history.db, logs). Keeps it separate from the scoring code.
- No framework code in the repo. The evaluator, server, and leaderboard logic come from the installed `autoanything` package.
- `problem.yaml` carries all configuration (base branch, timeout, branch pattern) instead of relying on hardcoded constants.

## What the Framework Provides

The `autoanything` package provides:

### CLI Commands

| Command | Description |
|---------|-------------|
| `autoanything init <name>` | Scaffold a new problem directory with templates |
| `autoanything score` | Run `scoring/score.sh` once and print the result (sanity check) |
| `autoanything evaluate` | Start the polling evaluator (watches for proposal branches) |
| `autoanything evaluate --baseline-only` | Establish baseline score and exit |
| `autoanything serve` | Start the webhook server (receives PR events) |
| `autoanything leaderboard` | Regenerate `leaderboard.md` from history |
| `autoanything history` | Print evaluation history from the DB |
| `autoanything validate` | Check that the problem directory is well-formed |

All commands operate on the current directory by default (overridable with `--dir`).

### Package Structure

```
src/autoanything/
├── __init__.py
├── cli.py                  # CLI entry point (click or argparse)
├── evaluator.py            # polling evaluation loop
├── server.py               # webhook server (FastAPI)
├── scoring.py              # run score.sh, parse JSON output
├── problem.py              # parse + validate problem.yaml (proper YAML)
├── leaderboard.py          # render leaderboard.md from history
├── history.py              # SQLite history management
├── git.py                  # git operations (fetch, merge, branch listing)
└── templates/              # scaffolding templates for `init`
    ├── problem.yaml
    ├── agent_instructions.md
    ├── score.sh
    ├── solution.py
    └── gitignore            # template for problem repo .gitignore
```

### Dependencies (framework only)

```
pyyaml          # proper YAML parsing
fastapi         # webhook server
uvicorn         # ASGI server
click           # CLI framework
```

No numpy, no torch, no tiktoken. Problem-specific deps belong to the problem, not the framework.

## Configuration: `problem.yaml`

`problem.yaml` becomes the single source of truth for both problem definition and evaluator behavior. Properly parsed with PyYAML, validated on load.

```yaml
name: my-problem
description: >
  One-paragraph description of what agents are optimizing.

# What agents can and cannot modify
state:
  - state/solution.py

context:
  - context/background.py

# Scoring configuration
score:
  name: cost                    # metric key in score.sh JSON output
  direction: minimize           # "minimize" or "maximize"
  description: "Total cost"     # human-readable, shown on leaderboard
  timeout: 900                  # seconds before scoring is killed (default: 900)
  script: scoring/score.sh      # path to scoring script (default: scoring/score.sh)

# Git configuration
git:
  base_branch: main             # branch that tracks the best state (default: main)
  proposal_pattern: "proposals/*"  # branch pattern for proposals (default: proposals/*)

# Constraints (documentation for agents, not enforced by framework)
constraints:
  - "All values must be finite"
  - "Solution must be a list of exactly 10 floats"
```

All fields under `git:` and `score:` have sensible defaults. A minimal `problem.yaml` is just:

```yaml
name: my-problem
description: Minimize the cost function.
state:
  - state/solution.py
score:
  name: cost
  direction: minimize
```

## What Stays the Same

The architectural choices that make AutoAnything elegant should not change:

- **Git as the protocol.** Anything that can `git push` can be an agent. This is the project's best design decision. No custom APIs, no agent SDKs, no registration. Push a branch, get scored.
- **Serial evaluation.** One proposal scored at a time. No race conditions, no stale comparisons. Simple and correct.
- **Blind scoring.** Agents never see the scoring code. Same reason Kaggle keeps the test set private — it prevents overfitting to the test harness.
- **score.sh → JSON.** The scoring interface is "run a shell script, get JSON on the last line." This is trivially implementable for any problem in any language. No framework-specific scoring API to learn.
- **Leaderboard as markdown.** Human-readable, version-controlled, auto-updated. Agents can parse it, humans can read it on GitHub.
- **SQLite history.** Lightweight, zero-config, portable. One file captures the full evaluation history.

## What This Unlocks

### Multi-problem

A user can run evaluators for several problems simultaneously. Each problem is its own directory with its own history, leaderboard, and scoring. No conflicts.

```bash
# Terminal 1
cd problems/prompt-optimization && autoanything evaluate

# Terminal 2
cd problems/model-architecture && autoanything evaluate
```

### Shareable problems

A problem is a git repo. Onboarding is:

```bash
git clone https://github.com/someone/their-problem
cd their-problem
autoanything evaluate --baseline-only
autoanything evaluate
```

The problem author ships the repo with state/, context/, problem.yaml, and a .gitignore that excludes scoring/. They send the scoring code out-of-band (or keep it on the evaluation machine).

### Framework updates

```bash
pip install --upgrade autoanything
```

Evaluator improvements, new CLI commands, bug fixes — all delivered without touching problem repos.

### Problem ecosystem

People can publish problems as repos. The `autoanything` CLI is the common runtime. A community can form around shared problems, like Kaggle competitions but fully open and self-hosted.

## What Happens to the Current Test Problems

The four test problems (rastrigin, tsp, packing, gpt) move from `test_problems/` to `examples/` in the framework repo. They serve as:

1. **Examples** for people creating their own problems.
2. **Integration tests** for the framework.
3. **Demo problems** for trying out AutoAnything.

Each becomes a self-contained problem directory:

```
examples/
├── rastrigin/
│   ├── problem.yaml
│   ├── agent_instructions.md
│   ├── state/solution.py
│   ├── context/problem.py
│   └── scoring/score.sh
├── tsp/
│   ├── ...
├── packing/
│   ├── ...
└── gpt/
    ├── ...
```

The `activate.sh` script is removed. The `run_test.py` simulation script becomes `autoanything test` or stays as a standalone script in the examples.

## Backward Compatibility

The current test problems and evaluate.py/server.py continue to work during the transition. The migration is additive — the new CLI wraps the same logic, just decoupled from hardcoded paths.

The `scoring/score.sh` convention is new, but the framework should also look for `evaluator/score.sh` as a fallback during a transition period. This can be dropped in a future version.

---

## Implementation Plan

### Phase 1: Proper Configuration (small, no structural changes)

**Goal:** Replace fragile string-matching YAML parsing with a real parser. Make hardcoded values configurable. This is a prerequisite for everything else and delivers immediate reliability gains.

**Steps:**

1. Add `pyyaml` to dependencies in `pyproject.toml`.

2. Create `autoanything/problem.py` — a module that loads and validates `problem.yaml`:
   - Parse with `yaml.safe_load()`.
   - Return a dataclass/dict with all fields, applying defaults:
     - `score.direction` → `"minimize"`
     - `score.timeout` → `900`
     - `score.script` → `"scoring/score.sh"` (fall back to `"evaluator/score.sh"`)
     - `git.base_branch` → `"main"` (fall back to `"master"` if `main` doesn't exist)
     - `git.proposal_pattern` → `"proposals/*"`
   - Validate required fields: `name`, `state` (non-empty list), `score.name`, `score.direction`.
   - Raise clear errors on missing or invalid fields.

3. Update `evaluate.py` to use `autoanything/problem.py` instead of `load_direction()` and `load_score_name()`:
   - Replace `MAIN_BRANCH = "master"` with value from problem config.
   - Replace hardcoded `"proposals/*"` pattern with value from problem config.
   - Replace hardcoded 15-minute timeout with value from problem config.
   - Replace hardcoded `SCORE_SCRIPT` path with value from problem config.

4. Update `server.py` to use the same config loader:
   - Replace its own `problem.yaml` parsing for `mutable:` validation.
   - Use the same base branch and score config.

5. Update test problems' `problem.yaml` files to use the full schema (add `git:` section where needed).

**Validation:** Run `run_test.py` for all three instant problems. Evaluator behavior should be identical.

### Phase 2: Extract the Package (the real refactor)

**Goal:** Move evaluator logic into an installable `autoanything` package with a CLI entry point. The evaluator scripts become thin wrappers or go away entirely.

**Steps:**

1. Restructure the repo:
   ```
   autoanything/
   ├── src/autoanything/        # NEW — the installable package
   │   ├── __init__.py
   │   ├── cli.py
   │   ├── evaluator.py         # extracted from evaluator/evaluate.py
   │   ├── server.py            # extracted from evaluator/server.py
   │   ├── scoring.py           # score.sh execution + JSON parsing
   │   ├── problem.py           # from Phase 1
   │   ├── leaderboard.py       # extracted from evaluate.py
   │   ├── history.py           # SQLite operations extracted from evaluate.py
   │   └── git.py               # git operations extracted from evaluate.py
   ├── examples/                # RENAMED from test_problems/
   │   ├── rastrigin/
   │   ├── tsp/
   │   ├── packing/
   │   └── gpt/
   ├── tests/                   # framework tests
   ├── pyproject.toml           # framework deps only
   └── README.md
   ```

2. Extract modules from `evaluate.py`:
   - `history.py`: `init_db()`, `record_evaluation()`, `get_incumbent()`, `update_incumbent()`, `is_evaluated()`. Pure SQLite operations, no git or scoring knowledge.
   - `scoring.py`: `run_score()`, JSON parsing logic. Takes a script path and timeout, returns parsed metrics.
   - `leaderboard.py`: `export_leaderboard()`. Takes history DB path, problem config, output path.
   - `git.py`: `git()` helper, `get_proposal_branches()`, merge operations. Takes base branch and proposal pattern as parameters (from config, not hardcoded).
   - `evaluator.py`: the main loop, now composing the above modules. Takes a problem config object instead of reading hardcoded paths.

3. Extract `server.py` similarly — it already imports from `evaluate.py`, so it naturally becomes a thin layer over the extracted modules.

4. Build the CLI (`cli.py`):
   - Use `click` (or `argparse` to avoid the dep).
   - Each command loads `problem.yaml` from the current directory (or `--dir` override).
   - `autoanything evaluate` replaces `uv run evaluator/evaluate.py`.
   - `autoanything serve` replaces `uv run evaluator/server.py`.
   - `autoanything score` runs score.sh once and prints the result.
   - `autoanything history` queries the DB and prints a table.
   - `autoanything validate` checks problem directory structure.

5. Update `pyproject.toml`:
   - Add `[project.scripts]` entry point: `autoanything = "autoanything.cli:main"`.
   - Move framework deps (fastapi, uvicorn, pyyaml) to main dependencies.
   - Remove problem-specific deps (numpy, torch, tiktoken, etc.) from the framework.
   - Add a `[project.optional-dependencies]` section for examples/dev.

6. Make evaluator state location configurable:
   - Default: `.autoanything/history.db` in the problem directory.
   - Configurable via `--db` flag or env var.

7. Update `.gitignore` template to exclude `scoring/`, `.autoanything/`.

**Validation:** `pip install -e .` in the repo, then `cd examples/rastrigin && autoanything evaluate --baseline-only` works.

### Phase 3: Scaffolding and Init (polish)

**Goal:** `autoanything init` creates a ready-to-use problem directory. New users go from zero to a working problem in under a minute.

**Steps:**

1. Create template files in `src/autoanything/templates/`:
   - `problem.yaml` — with placeholder values and comments explaining each field.
   - `agent_instructions.md` — generic protocol, references problem.yaml for specifics.
   - `score.sh` — skeleton that shows the JSON output convention.
   - `solution.py` — minimal example state file.
   - `gitignore` — pre-configured to exclude `scoring/`, `.autoanything/`.

2. Implement `autoanything init <name>`:
   - Creates the directory structure.
   - Copies templates with name substitution.
   - Initializes a git repo (`git init`).
   - Prints next-steps instructions.
   - Optional flags: `--metric <name>`, `--direction <min|max>` to pre-fill problem.yaml.

3. Implement `autoanything validate`:
   - Checks that `problem.yaml` exists and parses correctly.
   - Checks that all files listed in `state:` exist.
   - Checks that `score.sh` (or configured script) exists and is executable.
   - Checks that `.gitignore` excludes scoring directory.
   - Prints clear pass/fail with actionable error messages.

**Validation:** `autoanything init test-problem && cd test-problem && autoanything validate` passes.

### Phase 4: Migration and Cleanup

**Goal:** Remove the old structure, update documentation, ensure backward compatibility during transition.

**Steps:**

1. Remove `activate.sh`.

2. Remove `evaluator/evaluate.py` and `evaluator/server.py` from the repo root (they now live in the package). Keep `evaluator/` in the gitignore since problem repos will use `scoring/` instead.

3. Convert `test_problems/run_test.py` into either:
   - `autoanything test` CLI command, or
   - A standalone script in `examples/` that imports from the `autoanything` package.

4. Move `test_problems/plot_progress.py` to `src/autoanything/` or make it a CLI command (`autoanything plot`).

5. Update README.md:
   - Installation: `pip install autoanything`
   - Quick start: `autoanything init`, edit files, `autoanything evaluate`
   - Link to examples for reference problems.

6. Update CLAUDE.md to reflect new structure and commands.

7. Add a `MIGRATING.md` for anyone who forked the old structure, explaining:
   - Move your problem files into their own directory.
   - Move `evaluator/score.sh` to `scoring/score.sh`.
   - Install `autoanything` and use CLI commands instead of running scripts directly.
   - The `evaluator/` directory at repo root is no longer needed.

### Phase 5: Extended Features (future, not blocking)

Ideas that become natural once the framework exists, but aren't needed for launch:

- **`autoanything leaderboard --serve`**: Live-updating web leaderboard (the server already has FastAPI, add a simple HTML endpoint).
- **Problem registries**: `autoanything clone <url>` that clones a problem repo and validates its structure.
- **Agent helpers**: A small `autoanything-agent` package that agents can optionally install for utilities (parse leaderboard, read problem config, generate branch names).
- **Multi-evaluator**: `autoanything evaluate --problems ./p1 ./p2 ./p3` to run evaluators for multiple problems in one process.
- **Notifications**: Slack/Discord webhooks when a new best score is found.
- **Scoring containers**: `autoanything evaluate --docker` to run score.sh in an isolated container (security for untrusted agent submissions).
