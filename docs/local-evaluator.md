# Local Evaluator

The local evaluator is the simplest AutoAnything deployment target. It lives in a gitignored `evaluator/` directory and owns the private scoring code, SQLite history, and any hidden test assets.

## Public exports

After each evaluation the evaluator refreshes:

- `leaderboard.md`
- `history/attempts.json`
- `dashboard.html`
- `signals.md`
- `signals.json`
