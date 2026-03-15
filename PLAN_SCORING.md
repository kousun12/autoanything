# Plan: Branch-Based Scoring

## Context

Scoring code (`scoring/score.py`) is the black-box metric that drives optimization. Agents must never see it. Today this is enforced two ways:

1. **Gitignore**: `scoring/` is in `.gitignore`, so it's never committed to working branches.
2. **Physical hide/restore** (local loop only): During `autoanything run`, `runner.py` uses `shutil.move()` to relocate `scoring/` to `.autoanything/_scoring/` before the agent runs, then moves it back for scoring.

The hide/restore approach is a filesystem mutation that can go wrong if the process is interrupted. Recovery logic exists (`_recover_scoring` in `runner.py:58-64`), but it's the kind of thing that bites you. Scoring is also completely unversioned — it's an untracked file on disk with no history.

## Motivation

1. **Eliminate the hide/restore dance.** No more `shutil.move()` that can fail mid-operation. Scoring doesn't exist on working branches by construction — it lives on a dedicated git branch and is pulled on demand.

2. **Version-controlled scoring.** Currently if the evaluator's disk dies, scoring is gone. With a branch, scoring has full git history, diffs, and is distributed with `git clone`.

3. **Scoring experimentation.** Different scoring branches enable A/B testing of scoring functions. `--scoring-branch scoring/v2` on the CLI switches the metric entirely — no code changes, no file swaps. Two evaluators can run simultaneously with different scoring functions against the same problem.

4. **Multi-evaluator consistency.** Multiple machines running evaluation currently need `scoring/score.py` distributed out of band. With branch-based scoring, `git fetch` is all you need.

5. **Cleaner agent isolation.** Agents can't accidentally see scoring because it doesn't exist on any working branch. No filesystem tricks needed, no recovery logic.

## Design

### Core concept

Scoring code lives on a dedicated orphan branch (default: `scoring`). Working branches (main, proposals/*) never have `scoring/` committed. The `.gitignore` still excludes `scoring/` as a safety net.

When the evaluator needs to score:

```python
# 1. Overlay scoring from the scoring branch into the working tree
git("checkout", scoring_branch, "--", "scoring/", cwd=problem_dir)

# 2. Run scoring (unchanged — still imports from scoring.score, cwd=problem_dir)
score_val, metrics, duration, error = run_score(problem_dir, ...)

# 3. Clean up — remove overlay and unstage
shutil.rmtree(os.path.join(problem_dir, "scoring"))
git("reset", "HEAD", "--", "scoring/", cwd=problem_dir)
```

This is a context manager:

```python
@contextmanager
def scoring_context(problem_dir: str, scoring_branch: str = "scoring"):
    """Temporarily overlay scoring code from the scoring branch."""
    scoring_dir = os.path.join(problem_dir, "scoring")
    # Clean up stray scoring dir from a previous interrupted run
    if os.path.isdir(scoring_dir):
        shutil.rmtree(scoring_dir)
    git("checkout", scoring_branch, "--", "scoring/", cwd=problem_dir)
    try:
        yield
    finally:
        if os.path.isdir(scoring_dir):
            shutil.rmtree(scoring_dir)
        git("reset", "HEAD", "--", "scoring/", cwd=problem_dir, check=False)
```

### Failure mode comparison

| Scenario | Current (hide/restore) | Branch-based |
|----------|----------------------|-------------|
| Interrupted during agent run | `scoring/` is missing; needs `_recover_scoring()` to move it back from `.autoanything/_scoring/` | `scoring/` doesn't exist — nothing to recover |
| Interrupted during scoring | `scoring/` is present; fine | Stray `scoring/` dir — gitignored, deleted on next run |
| Concurrent runs | Both try to move the same directory — race condition | Both checkout from branch — safe (separate working trees) |

### Config changes

`problem.yaml` gains an optional field:

```yaml
score:
  name: score
  direction: minimize
  branch: scoring        # NEW — default "scoring"
```

CLI commands gain `--scoring-branch` to override:

```bash
autoanything run -a "./agent.sh" --scoring-branch scoring/v2
autoanything evaluate --scoring-branch scoring/experimental
autoanything serve --scoring-branch scoring/strict
autoanything score --scoring-branch scoring    # default
```

### `autoanything init` changes

Init creates the scoring branch as an orphan branch with the template `score.py`:

```bash
git checkout --orphan scoring
git rm -rf .              # clean slate
# write scoring/score.py
git add scoring/
git commit -m "Initial scoring function"
git checkout main
```

The result: `main` has no `scoring/` directory; `scoring` branch has only `scoring/score.py`. The `.gitignore` on `main` still lists `scoring/` as a safety net.

### Backwards compatibility

Support both modes with a simple priority:

1. If `--scoring-branch` is passed, use it.
2. If `score.branch` is set in `problem.yaml`, use it.
3. If neither is set and a local `scoring/` directory exists on disk, use it directly (legacy mode — no branch checkout needed).
4. If neither is set and no local `scoring/` exists, try the `scoring` branch by convention.

This means existing problems with `scoring/` on disk keep working with zero changes. The migration path is: move your `scoring/` onto a branch when you're ready.

---

## Implementation Plan

### Phase 1: Scoring context manager (new utility)

**Files:**
- `src/autoanything/scoring.py` — add `scoring_context()` context manager and a helper `resolve_scoring_branch()` that implements the priority logic above
- `src/autoanything/problem.py` — add optional `branch` field to `ScoreConfig` (default: `None`)

**`scoring_context` behavior:**
- Takes `problem_dir`, `scoring_branch` (optional)
- If `scoring_branch` is `None` and `scoring/` exists on disk, yield immediately (legacy mode — no-op)
- If `scoring_branch` is `None` and `scoring/` does not exist, try branch named `scoring`
- If a branch is specified or resolved, checkout `scoring/` from that branch, yield, then clean up
- On cleanup: `shutil.rmtree(scoring/)` + `git reset HEAD -- scoring/` to unstage
- On entry: if stray `scoring/` exists, remove it first (recovery from interrupted run)

**`ScoreConfig` change:**
- Add `branch: str | None = None` field
- Parse from `score.branch` in `problem.yaml`

**Tests:**
- `tests/test_scoring.py` — add tests for `scoring_context`:
  - Legacy mode: `scoring/` on disk, no branch → no-op
  - Branch mode: no `scoring/` on disk, branch exists → checks out and cleans up
  - Cleanup on exception: scoring dir removed even if inner code raises
  - Recovery: stray `scoring/` dir cleaned up on entry

### Phase 2: Wire into runner.py

**Files:**
- `src/autoanything/runner.py` — replace hide/restore with `scoring_context`

**Changes:**
- Delete `_scoring_dir()`, `_hidden_path()`, `_hide_scoring()`, `_restore_scoring()`, `_recover_scoring()` (lines 25-64, ~40 lines removed)
- In `run_local()`:
  - Remove `_recover_scoring()` call at the top
  - Remove the `_hide_scoring` / `_restore_scoring` bracket around agent execution (lines 159-177). Agent runs no longer need scoring hidden — it doesn't exist on working branches.
  - Wrap the `run_score()` call (line 231-233) in `scoring_context()`
  - Remove `_recover_scoring()` from the `KeyboardInterrupt` handler
- Accept `scoring_branch` parameter in `run_local()`, passed from CLI

**Before (current):**
```python
hidden = _hide_scoring(problem_dir)
try:
    subprocess.run(agent_command, ...)
finally:
    if hidden:
        _restore_scoring(problem_dir)

# ... later ...
score_val, metrics, duration, error = run_score(problem_dir, ...)
```

**After:**
```python
subprocess.run(agent_command, ...)

# ... later ...
with scoring_context(problem_dir, scoring_branch):
    score_val, metrics, duration, error = run_score(problem_dir, ...)
```

**Tests:**
- No dedicated `test_runner.py` exists currently; runner tests would be integration-level
- Existing `test_scoring.py` tests for `run_score` remain unchanged
- The `scoring_context` tests from Phase 1 cover the new logic

### Phase 3: Wire into evaluator.py and server.py

**Files:**
- `src/autoanything/evaluator.py` — wrap `run_score` calls in `scoring_context`
- `src/autoanything/server.py` — wrap `run_score` calls in `scoring_context`

**evaluator.py changes:**
- `establish_baseline()` (line 57): wrap `run_score` call in `scoring_context()`
- `evaluate_proposal()` (line 114): wrap `run_score` call in `scoring_context()`
- Accept `scoring_branch` parameter, threaded from `run_evaluator()` and CLI

**server.py changes:**
- `_evaluate_one_pr()` (line 251): wrap `run_score` call in `scoring_context()`
- Thread `scoring_branch` through `create_app()` → worker → `_evaluate_one_pr()`

**Tests:**
- `tests/test_evaluator.py` — mock targets stay the same (`autoanything.evaluator.run_score`). The `scoring_context` is tested separately. These tests mock `run_score` so they don't exercise the context manager — that's fine, it's tested in Phase 1.
- `tests/test_server.py` — same story; the server tests mock at a higher level

### Phase 4: CLI and init changes

**Files:**
- `src/autoanything/cli.py` — add `--scoring-branch` option to `run`, `evaluate`, `serve`, `score`, `validate`; update `init` to create scoring branch

**CLI option (shared):**
```python
@click.option("--scoring-branch", default=None,
              help="Git branch containing scoring/ (default: auto-detect)")
```

Added to: `run`, `evaluate`, `serve`, `score`, `validate`.

**`init` command changes:**
- After creating the problem directory and git repo on `main`:
  - Create orphan branch `scoring`
  - Write `scoring/score.py` from template
  - Commit
  - Switch back to `main`
- The `scoring/` directory on `main` is created only if needed for backwards compat, or omitted entirely (preferred — cleaner)
- Update printed "Next steps" to mention the scoring branch:
  ```
  # Edit scoring: git checkout scoring && edit scoring/score.py && git commit && git checkout main
  ```

**`score` command changes:**
- Wrap `run_score` call in `scoring_context(problem_dir, scoring_branch)`

**`validate` command changes:**
- Instead of checking for `scoring/score.py` on disk, also check the scoring branch
- If neither exists, error
- If scoring is on a branch, report that (not a warning)
- Adjust the "scoring tracked by git" check — on the scoring branch it's expected; on main it's still a warning

**Tests:**
- `tests/test_cli.py`:
  - `TestInit`: update `test_creates_scoring_dir` and `test_creates_score_py` — scoring now lives on a branch, not on disk on main. Add test that `git branch` output includes `scoring`.
  - `TestValidate`: update `test_missing_score_py_fails` to account for branch-based scoring. Add test for branch-based validation.
  - `TestScore`: update to work with scoring on a branch (may need a git repo fixture)
- `tests/test_integration.py`:
  - `TestInitToScore`: update — after init, scoring is on a branch. The test should checkout scoring, write the real `score()`, commit, checkout main, then run `autoanything score`.
- `tests/conftest.py`:
  - `problem_dir` fixture: add a `scoring` branch with `scoring/score.py` in addition to (or instead of) the on-disk scoring directory. For backwards-compat tests, keep the on-disk variant as a separate fixture.

### Phase 5: Template and doc updates

**Files:**
- `src/autoanything/templates/gitignore` — keep `scoring/` (now serves as a safety net rather than the primary mechanism)
- `src/autoanything/templates/problem.yaml` — add commented-out `branch: scoring` under `score:`
- `CLAUDE.md` — update "How Problems Work" section, evaluator design notes, and any references to scoring being gitignored
- `SCORE_DOCS.md` — update the "basics" section to explain branch-based scoring, add section on scoring experimentation via branches
- `agent_instructions.md` — no changes needed (agents already can't see scoring)
- `README` or repo docs — if they exist, update references

**Template changes:**

`templates/problem.yaml`:
```yaml
score:
  direction: {{direction}}
  description: "Describe what this metric measures"
  # name: score             # metric key, default "score"
  # timeout: 900            # seconds before scoring is killed
  # branch: scoring         # git branch with scoring/ (default "scoring")
  # bounded: false          # true if the metric has a known optimum
```

`templates/gitignore` (unchanged — scoring/ exclusion remains as safety net):
```
# Scoring code lives on the "scoring" branch — this is a safety net
scoring/

# Evaluator state (history database, logs)
.autoanything/
```

**CLAUDE.md updates:**
- Problem structure diagram: note that `scoring/` lives on a dedicated branch, not on main
- Evaluator design: replace "Blind scoring: agents never see scoring/ (gitignored; physically hidden during run)" with "Blind scoring: scoring code lives on a dedicated branch and is overlaid only during evaluation"
- Add note about `--scoring-branch` for experimentation

**SCORE_DOCS.md updates:**
- "The basics" section: explain that `scoring/score.py` lives on the `scoring` branch
- Add new section: "Scoring branches" explaining how to use different branches for experimentation
- Update setup workflow: `git checkout scoring` → edit → commit → `git checkout main`

---

## Migration path for existing problems

Existing problems with `scoring/` on disk continue to work unchanged (legacy mode in `scoring_context`). To migrate:

```bash
cd my-problem

# Create the scoring branch from current scoring files
git checkout --orphan scoring
git rm -rf .
cp /path/to/your/scoring scoring/  # or move from backup
git add scoring/
git commit -m "Move scoring to dedicated branch"
git checkout main

# Verify
autoanything score   # should auto-detect the scoring branch
```

No changes to `problem.yaml` are required — the default branch name `scoring` is resolved by convention.

## Open questions

1. **Orphan branch vs regular branch?** Orphan keeps the scoring branch's history completely separate from main's history. Regular branch means scoring shares the initial commit with main. Orphan is cleaner but slightly more ceremony. Recommendation: orphan.

2. **Should `autoanything edit-scoring` be a convenience command?** Switching to the scoring branch, editing, committing, and switching back is more ceremony than editing a local file. A helper command could smooth this. Could be a fast follow-up, not required for the initial implementation.

3. **Remote scoring branches.** For problems hosted on GitHub, the scoring branch would be pushed. This means anyone with repo access can see the scoring code (on that branch). This is fine for most use cases but worth noting — if scoring must be truly secret, the branch can be kept local or in a separate private repo. Not a blocker.
