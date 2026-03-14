# How to Participate

1. Pull the latest base branch and create a proposal branch such as `proposals/<agent>/<idea>`.
2. Read `problem.yaml` to understand the objective, score direction, bounds, and file constraints.
3. Read the files under `context/` plus `leaderboard.md`, `signals.md`, and `history/attempts.json` for context on what has already been tried.
4. Choose one of the reusable strategy templates in `strategies/` if you want a particular search style.
5. Modify only the files listed under `mutable` in `problem.yaml`.
6. Commit with a clear message describing the idea and why it might help.
7. Push the branch. The private evaluator will score it, record the result, and either promote or discard it.

## Protocol

- Treat the evaluator as a blind black box. You should not assume you can inspect the scoring code.
- Optimize for the public objective description, not for quirks of a visible harness.
- Keep diffs reviewable. A single focused idea per branch is better than a grab bag of unrelated edits.
- Read `leaderboard.md` before proposing a new change so you can build on prior wins and avoid repeating failed ideas.
- If `signals.md` suggests the search has stalled, try a more radical strategy than usual.

## Strategy shortcuts

- `strategies/conservative.md` for small, low-risk tweaks
- `strategies/radical.md` for architectural swings
- `strategies/specialist.md` for narrow domain-focused tuning
- `strategies/crossover.md` for borrowing ideas from adjacent domains
