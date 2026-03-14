# AutoAnything: Plan for Generalizing Autoresearch

## The Idea

Autoresearch proves a powerful concept: an AI agent can autonomously improve a system by proposing changes, scoring them against an objective metric, and keeping only what works. But right now it's welded to one domain — optimizing a GPT training script against val_bpb on a single GPU — and it's serial, single-agent, all on one machine.

The concept generalizes to *any* optimization problem with a black-box scoring function. AutoAnything is a framework where you define what to optimize and how to score it, then unleash a swarm of agents — potentially hundreds, running in different sandboxes, different machines, different continents — to hill-climb relentlessly. You come back in a week to a leaderboard of experiments and a measurably better system.

**Examples of things you could optimize:**

- A prompt template (scored by LLM-as-judge accuracy on a test set)
- A web app's Lighthouse performance score
- A compiler optimization pass (scored by benchmark runtime)
- A trading strategy (scored by backtested Sharpe ratio)
- An infrastructure config (scored by p99 latency under load)
- A game AI (scored by win rate against a baseline opponent)
- An ML training script (the original use case)

The common pattern: there's some mutable state (files an agent can change), an evaluation function that produces a number, and a direction (lower is better, or higher is better). Everything else is details.

## The Critical Design Insight: Blind Evaluation

The most important architectural decision is the separation between **what agents can see** and **how scoring works**.

Agents must NOT have access to the scoring function. If they can see the evaluator, they can game it — overfitting to the test set, exploiting quirks in the metric, or just hardcoding good scores. This is the same reason Kaggle keeps the test set private.

This means the system is fundamentally **two separate things**:

1. **The Challenge Repo** (public/shared) — the mutable files, agent instructions, score history, and a description of what "better" means in plain language. This is what agents clone and work in. The scoring function is NOT here.

2. **The Evaluator** (private) — the scoring code, evaluation infrastructure, and merge logic. Only the problem owner controls this. It runs somewhere agents can't see into — a private server, a GitHub Action with secrets, a separate machine.

Agents submit their work by **pushing a git branch** (or opening a PR). They describe what they tried. The evaluator picks it up, scores it in private, and decides whether to merge it forward.

This is Kaggle for code. The leaderboard is public, the test set is private, and submissions are git branches.

## Architecture

```
                    ┌──────────────────────────────────┐
                    │         Challenge Repo            │
                    │         (public/shared)           │
                    │                                   │
                    │  - mutable files (e.g. train.py)  │
                    │  - agent instructions              │
                    │  - leaderboard / history           │
                    │  - problem description             │
                    │  - NO scoring code                 │
                    └──────────┬───────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
         push branch      push branch      push branch
              │                │                │
        ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
        │  Agent 1   │   │  Agent 2   │   │  Agent N   │
        │  (sandbox) │   │  (sandbox) │   │  (sandbox) │
        │            │   │            │   │            │
        │ clones repo│   │ clones repo│   │ clones repo│
        │ makes edits│   │ reads hist │   │ tries idea │
        │ pushes     │   │ pushes     │   │ pushes     │
        └────────────┘   └────────────┘   └────────────┘

                               │
                     ┌─────────┴──────────┐
                     │     Evaluator       │
                     │     (private)       │
                     │                     │
                     │ - watches for new   │
                     │   branches / PRs    │
                     │ - has scoring code  │
                     │ - runs evaluation   │
                     │ - posts score       │
                     │ - merges or rejects │
                     └─────────────────────┘
```

### The Challenge Repo

This is an ordinary git repo (typically on GitHub). It contains:

```
challenge-repo/
├── problem.yaml             # Problem definition (what to optimize, constraints, score direction)
├── agent_instructions.md    # Guidance for agents (like program.md but generic)
├── leaderboard.md           # Auto-updated scoreboard
├── history.tsv              # Full experiment log (commit, score, status, description)
│
├── src/                     # The mutable files agents can edit
│   └── train.py             # (or whatever the problem's mutable state is)
│
└── context/                 # Read-only files agents can reference
    └── prepare.py           # (or whatever immutable context the problem needs)
```

**`problem.yaml`** tells agents what they're optimizing and what files they can touch. It does NOT contain the evaluation command or scoring code:

```yaml
name: gpt-pretraining
description: >
  Optimize a GPT training script for lowest validation bits-per-byte (val_bpb).
  Training runs for a fixed 5-minute time budget. You can change anything in the
  mutable files: model architecture, optimizer, hyperparameters, batch size, etc.
  The evaluation metric is val_bpb — lower is better.

mutable:
  - src/train.py

readonly:
  - context/prepare.py

score:
  direction: minimize
  name: val_bpb
  description: "Validation bits per byte — measures how well the model compresses unseen text"

constraints:
  - "Training must complete within the 5-minute time budget"
  - "Only packages in pyproject.toml are available"
  - "Must not modify files outside of src/"
```

**`agent_instructions.md`** is the generalized `program.md`. It tells agents the protocol:

```markdown
# How to Participate

1. Clone this repo and create a branch: `proposals/<your-name>/<short-description>`
2. Read `problem.yaml` to understand what you're optimizing
3. Read the files in `context/` for background
4. Read `history.tsv` and `leaderboard.md` to see what's been tried
5. Modify ONLY the files listed under `mutable` in `problem.yaml`
6. Commit with a clear message explaining your approach
7. Push your branch

The evaluator will automatically pick up your branch, score it, and post results.
If your score improves on the current best, your change will be merged to main.
```

**`history.tsv`** is the experiment log, updated by the evaluator after each run:

```
commit	branch	score	status	description	timestamp
a1b2c3d	main	0.997900	baseline	initial baseline	2026-03-13T10:00:00Z
b2c3d4e	proposals/agent-1/higher-lr	0.993200	accepted	increase LR to 0.04	2026-03-13T10:08:00Z
c3d4e5f	proposals/agent-2/gelu	1.005000	rejected	switch to GeLU activation	2026-03-13T10:12:00Z
d4e5f6g	proposals/agent-3/wider	0.000000	crash	double model width (OOM)	2026-03-13T10:15:00Z
```

### The Evaluator

The evaluator is a separate system that the problem owner runs. It watches the challenge repo for new branches/PRs, runs the scoring function, and decides whether to merge.

**The evaluator has its own private repo/config** that contains:

```
evaluator/
├── evaluator.yaml           # Evaluator configuration
├── score.sh                 # The actual scoring script (PRIVATE — agents never see this)
├── data/                    # Test data, validation sets, etc. (PRIVATE)
└── autoanything/            # The evaluator framework code
    ├── watcher.py           # Watches for new branches/PRs
    ├── runner.py             # Runs evaluations in isolation
    ├── merger.py             # Decides whether to merge, handles conflicts
    └── reporter.py          # Updates leaderboard, posts PR comments
```

**`evaluator.yaml`** configures the evaluator:

```yaml
challenge_repo: https://github.com/user/my-challenge.git
# Or a local path: challenge_repo: /path/to/challenge

# How to detect new submissions
watch:
  mode: poll           # poll | github-webhook | github-actions
  interval: 30s        # for poll mode
  branch_pattern: "proposals/**"

# Evaluation
evaluate:
  command: bash score.sh
  timeout: 600
  # Optional: run multiple evaluations per proposal for statistical significance
  # runs: 3
  # aggregate: median

# How to handle concurrent submissions and merges
merge:
  strategy: score-gated   # score-gated | rebase-and-reeval | manual
  # score-gated: accept if score beats current best, even if base has moved
  # rebase-and-reeval: always rebase onto latest main and re-evaluate
  # manual: post score but let a human decide whether to merge

# Where to post results
report:
  update_history: true     # append to history.tsv in challenge repo
  update_leaderboard: true # update leaderboard.md
  pr_comments: true        # post score as PR comment (if using PRs)
```

### How Evaluation Runs

When the evaluator detects a new branch:

1. **Checkout:** Clone/fetch the challenge repo, checkout the proposal branch into an isolated environment (worktree, container, temp dir)
2. **Inject scoring code:** The evaluator copies its private scoring script and any required data into the environment. The scoring code was never in the challenge repo — it only exists in the evaluator's private space.
3. **Run:** Execute the scoring command. Capture the score from stdout.
4. **Decide:** Compare the score against the current best on main.
5. **Act:**
   - If the score improved: merge the branch to main, update history.tsv and leaderboard.md, push.
   - If the score didn't improve: close/reject, record in history.tsv as rejected.
   - If the run crashed: record as crash, optionally notify the submitter.
6. **Clean up:** Remove the isolated environment.

### Deployment Options for the Evaluator

The evaluator can run in multiple ways, depending on the problem:

**Option A: GitHub Actions**

The most natural fit for GitHub-hosted challenges. A workflow triggers on PRs to the challenge repo. The scoring code lives in the evaluator's private repo (or as GitHub Action secrets/artifacts). The workflow checks out the PR, injects the scoring code, runs it, posts the score as a PR comment, and auto-merges if improved.

```yaml
# .github/workflows/evaluate.yml (in the challenge repo, but the scoring
# script is fetched from a private repo or secret at runtime)
on:
  pull_request:
    branches: [main]

jobs:
  evaluate:
    runs-on: ubuntu-latest  # or self-hosted with GPU
    steps:
      - uses: actions/checkout@v4
      - name: Fetch scoring code
        uses: actions/checkout@v4
        with:
          repository: user/my-evaluator-private
          token: ${{ secrets.EVALUATOR_TOKEN }}
          path: _evaluator
      - name: Run evaluation
        run: bash _evaluator/score.sh
      - name: Post results
        run: python _evaluator/autoanything/reporter.py
```

The scoring code repo is private. Agents can't see it. The GitHub Action runs in a fresh environment each time. Clean separation.

**Option B: Standalone Server**

An HTTP service running somewhere (a VM, a container, a machine with GPUs). It polls the challenge repo for new branches, evaluates them, and pushes results back.

Good for: expensive evaluations (GPU training), custom hardware, problems where you need persistent state between evaluations.

**Option C: Local**

Run the evaluator on your laptop. It watches a local clone of the challenge repo. Good for development and small-scale testing.

All three options use the same evaluator code — they differ only in how the watcher detects new submissions and how the runner isolates evaluation environments.

### Concurrency and Merge Strategy

Multiple agents pushing branches simultaneously is the expected case. The evaluator needs a strategy for what happens when multiple proposals are in flight and main is moving.

**Score-Gated (default, simple):**

Proposals are evaluated against the state of main at the time they were submitted. If a proposal's score beats the *current* best (which may have moved since the proposal was submitted), merge it. If not, reject.

This is optimistic — the proposal was developed and evaluated against an older state, and we're merging it onto a newer state. The change might interact badly with intervening accepted changes. But for most problems, small independent changes don't interfere, and the simplicity is worth it. If a merged change turns out to be bad (the next evaluation of main reveals a regression), the evaluator can detect this and revert.

```
Timeline:

main:    v1 ──────────── v2 (agent B merged) ──── v3 (agent A merged?)
              │                                    ↑
agent A:      └── proposes change ── scores 0.95 ──┘ (0.95 < v2's 0.96? accept)
              │
agent B:      └── proposes change ── scores 0.96 ──── merged as v2
```

**Rebase-and-Reeval (safe, expensive):**

Before merging, rebase the proposal onto current main and re-evaluate. Correct but doubles the evaluation cost for proposals that arrive while main is moving.

Good for: problems where changes interact heavily, or where evaluation is cheap enough that re-running is fine.

**Manual:**

Post the score, let a human decide. Good for high-stakes problems where you want human judgment in the loop.

## What the Current System Does Well (and What We Keep)

1. **Dead-simple protocol.** Modify → submit → get scored → keep/discard. We keep this.
2. **Git as the state machine.** Branches track proposals. Main tracks the best known state. We keep this and lean into it harder.
3. **Human-readable instructions.** `agent_instructions.md` is just Markdown. We keep this.
4. **Fixed evaluation budget.** Per-problem timeouts ensure comparability. We keep this as a configurable constraint.

## What Changes from the Current System

| Aspect | Autoresearch (current) | AutoAnything (target) |
|--------|----------------------|----------------------|
| Domain | ML training only | Any black-box optimization |
| Agents | 1, serial, same machine | N, parallel, distributed |
| Scoring | Agent runs eval and reads score | Evaluator runs privately, agent never sees scoring code |
| Submission | Agent modifies file in place, git commit | Agent pushes branch / opens PR |
| State management | Single branch, git reset on failure | Main branch = best state, proposal branches |
| Evaluation | Inline in the agent loop | Separate private service |
| History | Untracked results.tsv | Committed leaderboard + history in the challenge repo |

## Concrete Plan: From Here to There

### Phase 1: The Split

**Goal:** Separate the challenge repo from the evaluator. Get the existing ML use case working in this two-repo model.

1. **Restructure this repo as a challenge repo:**
   - Create `problem.yaml` with the ML problem definition (no scoring code)
   - Move `train.py` into `src/`
   - Move `prepare.py` into `context/`
   - Rewrite `program.md` → `agent_instructions.md` with the generic protocol (clone, branch, modify, push)
   - Add `history.tsv` and `leaderboard.md` (initially empty)

2. **Create a separate evaluator directory (or repo):**
   - `evaluator.yaml` pointing at this repo
   - `score.sh` that runs `uv run src/train.py`, extracts `val_bpb`
   - A minimal `watcher.py` that polls for new branches
   - A minimal `runner.py` that checks out a branch, injects the scoring script, runs it, captures the score
   - A minimal `merger.py` that compares score to current best and merges or rejects
   - A `reporter.py` that updates `history.tsv` and `leaderboard.md`

3. **Test end-to-end:** Manually create a proposal branch, run the evaluator, see it get scored and merged (or rejected).

**Deliverable:** The ML training optimization works through the new system. An agent can clone the challenge repo, make changes to `src/train.py`, push a branch, and the evaluator scores it and merges if better. The agent never sees `score.sh`.

### Phase 2: GitHub Actions Evaluator

**Goal:** Make evaluation happen automatically via GitHub infrastructure.

1. Write a GitHub Actions workflow that triggers on PRs to the challenge repo
2. The workflow fetches scoring code from a private repo (using a secret token)
3. It runs the evaluation, posts the score as a PR comment
4. If the score improves, it auto-merges the PR and updates the leaderboard
5. If not, it closes the PR with a comment explaining the score

**Deliverable:** Anyone (human or agent) can fork the challenge repo, make changes, open a PR, and get an automated score. The scoring function stays private.

For problems that need GPUs or special hardware, the GitHub Action can use self-hosted runners.

### Phase 3: Multi-Agent at Scale

**Goal:** Support many agents submitting concurrently, with intelligent coordination.

1. **Concurrency handling:** Implement the score-gated merge strategy so multiple PRs can be evaluated and merged without conflicts blocking progress
2. **Agent history feed:** The evaluator maintains a structured history that agents can read to learn what's been tried and what works. This goes beyond `history.tsv` — it could include diffs of accepted changes, diffs of rejected changes, and summaries.
3. **Rate limiting and fairness:** If hundreds of agents are submitting, the evaluator needs a queue with basic fairness (don't let one prolific agent starve others)
4. **Leaderboard and progress dashboard:** A web page (or GitHub Pages) showing the progress curve, top agents, recent experiments

### Phase 4: Intelligence and Diversity

**Goal:** Make the swarm smarter.

1. **Agent strategy templates:** Provide multiple `agent_instructions.md` variants that encourage different exploration strategies (conservative, radical, specialist, crossover)
2. **Structured feedback:** When the evaluator rejects a proposal, it can include more than just the score — e.g., "your change increased memory usage by 3x" or "training crashed at step 200 with OOM"
3. **Combination proposals:** An agent mode that fetches two recently-rejected proposals and tries to synthesize their approaches
4. **Diminishing returns signal:** The evaluator detects when the last N proposals all failed and publishes a "the low-hanging fruit is picked, try something radical" signal

### Phase 5: Generalize and Polish

**Goal:** Make it trivial to set up a new optimization challenge.

1. **`autoanything init`** — a CLI that scaffolds a new challenge repo from a template. Asks: "What files should agents modify? What does 'better' mean? Minimize or maximize?"
2. **`autoanything evaluator init`** — scaffolds the private evaluator config. Asks: "What command scores a proposal? Where should this run?"
3. **Second example problem** — something non-ML to prove generality (e.g., optimize a sorting algorithm for speed, optimize a CSS file for smallest bundle size, optimize a prompt for accuracy)
4. **Documentation and onboarding** for both problem owners (how to set up a challenge) and agents (how to participate)

## Key Design Decisions

### 1. Why git branches instead of an API?

- **Universal.** Anything that can `git push` can be an agent. A Claude Code session, a Codex agent, a human with vim, a shell script.
- **Auditable.** Every proposal is a commit with a diff and a message. The full history is in git.
- **No custom infrastructure for agents.** Agents don't need to speak HTTP to a coordinator. They just need git access to the challenge repo.
- **Works with GitHub's existing ecosystem.** PRs, Actions, code review, branch protections — all just work.

### 2. Why is the scoring function private?

- **Prevents gaming.** If agents can read the scoring function, they can overfit to it — finding inputs that score well by exploiting implementation details rather than genuinely improving.
- **Mirrors real optimization.** In real problems, you often *can't* see the scoring function. You're optimizing against user behavior, physical systems, or complex simulations. Training agents to work blind is more realistic and transferable.
- **Enables competition.** Multiple teams/agents can compete on the same challenge without anyone having an unfair advantage from seeing the test set.

### 3. How does the evaluator inject scoring code?

The evaluator checks out the proposal branch, then copies its private scoring scripts into the working directory before running them. The scoring scripts are never committed to the challenge repo. After evaluation, the working directory is destroyed.

For GitHub Actions: the scoring code lives in a private repo. The Action checks it out using a secret token into a temporary directory, runs it, and the runner is ephemeral.

For a standalone server: the scoring code lives on the server's filesystem. Each evaluation gets a fresh worktree or container with the proposal code, and the scoring script is bind-mounted or copied in.

### 4. What about the stale-base problem?

When Agent A starts from main@v5 and by the time it submits, main has advanced to v8:

**Score-gated:** Evaluate Agent A's branch as-is (based on v5). If the resulting score beats v8's score, cherry-pick/rebase the diff onto v8 and merge. The logic: if the change is good enough to beat the current best absolutely, it's probably still a good idea.

**If the cherry-pick has merge conflicts:** Reject the proposal. The agent can rebase onto current main and resubmit.

This keeps things simple and avoids expensive re-evaluation. For cheap evaluations, the evaluator can optionally re-eval after rebase.

### 5. What's the minimal viable system?

The smallest useful version is:

- A challenge repo with `problem.yaml`, one mutable file, and `agent_instructions.md`
- A single `evaluate.sh` script on the evaluator side that checks out branches, runs the scorer, and merges winners
- One agent (a Claude Code session) following the instructions

This is barely more complex than the current autoresearch setup, but it's structured for scale. You can add agents, switch to GitHub Actions, add a dashboard — all without changing the core protocol.

## What This Isn't

- **Not a hyperparameter search framework.** Optuna, Ray Tune, etc. search over numeric parameter spaces with mathematical strategies. AutoAnything uses LLM reasoning to make *arbitrary code/text changes*. The search space is unbounded and non-numeric.
- **Not CI/CD.** It doesn't deploy anything. It optimizes and logs results.
- **Not a competition platform.** It doesn't have user accounts, team management, or prize pools. It's a tool for running optimization, not a SaaS product. (Though someone could build a competition platform on top of it.)

## First Steps

1. Restructure this repo as a challenge repo (problem.yaml, src/, context/, agent_instructions.md)
2. Create the evaluator as a separate directory (evaluator/) with scoring script and minimal watcher/runner
3. Write a shell-script evaluator that polls for branches, scores them, merges or rejects
4. Test end-to-end with the existing ML use case
5. Write a GitHub Actions workflow as an alternative evaluator trigger
6. Create a second non-ML example to prove generality
