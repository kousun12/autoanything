"""Leaderboard and history rendering from the evaluation database."""

import sqlite3


def _render_table(rows, columns, lines):
    """Render rows as a markdown table."""
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join("---" for _ in columns) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")


def export_leaderboard(conn: sqlite3.Connection, output_path: str,
                       direction: str = "minimize"):
    """Export the leaderboard (top accepted scores) to a markdown file."""
    order = "ASC" if direction == "minimize" else "DESC"

    top = conn.execute(f"""
        SELECT score, branch, description, evaluated_at
        FROM evaluations WHERE status IN ('baseline', 'accepted')
        ORDER BY score {order}
    """).fetchall()

    lines = ["# Leaderboard", ""]
    rows = []
    for i, (score, branch, desc, when) in enumerate(top, 1):
        score_str = f"{score:.6f}" if score is not None else "crash"
        when_short = when[:16] if when else ""
        rows.append((i, score_str, branch, desc or "", when_short))
    _render_table(rows, ("#", "Score", "Branch", "Description", "When"), lines)
    lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def export_history(conn: sqlite3.Connection, output_path: str,
                   limit: int = 50):
    """Export recent evaluation history to a markdown file.

    Shows the most recent evaluations (accepted, rejected, crashed) so that
    agents can see what has been tried and learn from past attempts.
    """
    recent = conn.execute("""
        SELECT score, status, branch, description, evaluated_at
        FROM evaluations ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()

    lines = ["# History", ""]
    rows = []
    for score, status, branch, desc, when in recent:
        score_str = f"{score:.6f}" if score is not None else "crash"
        when_short = when[:16] if when else ""
        rows.append((score_str, status, branch, desc or "", when_short))
    _render_table(rows, ("Score", "Status", "Branch", "Description", "When"), lines)
    lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
