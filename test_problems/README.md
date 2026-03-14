# Test Problems

Three toy optimization problems for testing the AutoAnything framework. They require no GPU, no data download, and score instantly — perfect for developing and debugging the evaluator, agent protocol, and git workflow.

## Quick Start

```bash
# Activate a test problem (copies files into place)
bash test_problems/activate.sh rastrigin

# Verify scoring works
bash evaluator/score.sh

# Establish baseline and start evaluator
python evaluator/evaluate.py --baseline-only
python evaluator/evaluate.py

# Restore the real GPT pretraining problem when done
git checkout -- problem.yaml agent_instructions.md state/ context/
```

## Problems

### 1. Rastrigin Function Minimization (`rastrigin`)

**What:** Find the minimum of the [Rastrigin function](https://en.wikipedia.org/wiki/Rastrigin_function) in 10 dimensions.

**State:** `state/solution.py` — a list of 10 floats.

**Score:** `f(x) = 10n + sum(x_i^2 - 10*cos(2*pi*x_i))` — lower is better.

| Property | Value |
|----------|-------|
| Starting score | ~169.7 |
| Global optimum | 0.0 (all zeros) |
| Difficulty | Many local minima in a regular lattice |
| Scoring time | <1ms |

**Why it's good for testing:** Absolute minimum complexity. State is a list of numbers, scoring is a single function call. Tests the full loop (branch, score, merge/reject) without any possible infrastructure issues.

---

### 2. Traveling Salesman Problem (`tsp`)

**What:** Find the shortest tour visiting 20 fixed cities on a 200x200 grid.

**State:** `state/tour.py` — a permutation of `[0..19]`.

**Score:** Total Euclidean distance of the closed tour — lower is better.

| Property | Value |
|----------|-------|
| Starting score | ~1914 |
| Approximate optimum | ~680 |
| Difficulty | 20! possible permutations, combinatorial |
| Scoring time | <1ms |

**Why it's good for testing:** Slightly more complex state (permutation, not just numbers). Has a hard validity constraint (must be a valid permutation). Good for testing that agents respect constraints and that the evaluator handles invalid submissions gracefully.

---

### 3. Rectangle Packing (`packing`)

**What:** Pack 12 fixed-size rectangles into the smallest bounding box with no overlaps.

**State:** `state/packing.py` — a list of `(x, y, rotated)` placements.

**Score:** Bounding box area + 10000 per overlapping pair — lower is better.

| Property | Value |
|----------|-------|
| Starting score | 13250 |
| Theoretical minimum | 6975 (total rectangle area, assuming perfect packing) |
| Difficulty | Geometric reasoning, rotation choices |
| Scoring time | <1ms |

**Why it's good for testing:** More structured state (tuples with multiple fields). Has soft constraints (overlaps penalized, not rejected). Tests that agents can work with composite state and multi-objective scoring.

## File Structure

Each test problem mirrors the repo's main structure:

```
test_problems/<name>/
├── problem.yaml           # Problem definition
├── agent_instructions.md  # Protocol for agents
├── state/*.py             # Mutable file(s) agents edit
├── context/*.py           # Read-only context
└── evaluator/score.sh     # Scoring script
```

`activate.sh` copies these into the repo root. The evaluator (`evaluate.py`, `server.py`) is problem-agnostic — it reads the score key name from `problem.yaml` and delegates scoring to `score.sh`.

## Restoring the Real Problem

The GPT pretraining files are tracked by git. After testing:

```bash
git checkout -- problem.yaml agent_instructions.md state/ context/
```
