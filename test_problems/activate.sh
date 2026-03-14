#!/usr/bin/env bash
# activate.sh — Switch the repo to a test problem for development testing.
#
# Usage: bash test_problems/activate.sh <problem>
#
# Available problems: rastrigin, tsp, packing
#
# This copies the test problem's files into the repo root, replacing:
#   problem.yaml, agent_instructions.md, leaderboard.md,
#   state/*, context/*, evaluator/score.sh
#
# The original GPT pretraining files are tracked by git, so you can
# always restore them with: git checkout -- problem.yaml agent_instructions.md state/ context/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ $# -ne 1 ]; then
    echo "Usage: bash test_problems/activate.sh <problem>"
    echo ""
    echo "Available problems:"
    for d in "$SCRIPT_DIR"/*/; do
        name=$(basename "$d")
        [ -f "$d/problem.yaml" ] && echo "  $name"
    done
    exit 1
fi

PROBLEM="$1"
PROBLEM_DIR="$SCRIPT_DIR/$PROBLEM"

if [ ! -d "$PROBLEM_DIR" ] || [ ! -f "$PROBLEM_DIR/problem.yaml" ]; then
    echo "Error: unknown problem '$PROBLEM'"
    echo "Available: rastrigin, tsp, packing"
    exit 1
fi

echo "Activating test problem: $PROBLEM"

# Copy root-level files
cp "$PROBLEM_DIR/problem.yaml" "$REPO_ROOT/problem.yaml"
cp "$PROBLEM_DIR/agent_instructions.md" "$REPO_ROOT/agent_instructions.md"

# Reset leaderboard
cat > "$REPO_ROOT/leaderboard.md" << 'EOF'
# Leaderboard

No evaluations yet. Push a proposal branch to get started.
EOF

# Replace state/ contents
rm -f "$REPO_ROOT"/state/*.py
cp "$PROBLEM_DIR"/state/*.py "$REPO_ROOT/state/"

# Replace context/ contents
rm -f "$REPO_ROOT"/context/*.py
cp "$PROBLEM_DIR"/context/*.py "$REPO_ROOT/context/"

# Replace evaluator/score.sh
cp "$PROBLEM_DIR/evaluator/score.sh" "$REPO_ROOT/evaluator/score.sh"
chmod +x "$REPO_ROOT/evaluator/score.sh"

# Remove stale evaluator state
rm -f "$REPO_ROOT/evaluator/history.db"
rm -f "$REPO_ROOT/evaluator/run.log"

echo ""
echo "Done. Active problem: $PROBLEM"
echo ""
echo "Quick test:  bash evaluator/score.sh"
echo "Baseline:    python evaluator/evaluate.py --baseline-only"
echo ""
echo "To restore the GPT pretraining problem:"
echo "  git checkout -- problem.yaml agent_instructions.md state/ context/"
