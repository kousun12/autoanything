"""Leaderboard and history rendering from the evaluation database."""

import json
import sqlite3


def _render_entry(lines, score, branch, description, when, metrics_json,
                  heading_prefix=""):
    """Render a single evaluation entry as a markdown section."""
    score_str = f"{score:.6f}" if score is not None else "crash"
    when_short = when[:16] if when else ""

    lines.append(f"## {heading_prefix}{score_str}")
    lines.append("")
    if description:
        lines.append(description)
        lines.append("")
    lines.append(f"**Branch:** `{branch}`  ")
    lines.append(f"**Date:** {when_short}")
    if metrics_json:
        try:
            metrics = json.loads(metrics_json) if isinstance(metrics_json, str) else metrics_json
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(metrics, indent=2))
            lines.append("```")
        except (json.JSONDecodeError, TypeError):
            pass
    lines.append("")


def export_leaderboard(conn: sqlite3.Connection, output_path: str,
                       direction: str = "minimize"):
    """Export the leaderboard (top accepted scores) to a markdown file."""
    order = "ASC" if direction == "minimize" else "DESC"

    top = conn.execute(f"""
        SELECT score, branch, description, evaluated_at, metrics_json
        FROM evaluations WHERE status IN ('baseline', 'accepted')
        ORDER BY score {order}
    """).fetchall()

    lines = ["# Leaderboard", ""]
    for i, (score, branch, desc, when, metrics_json) in enumerate(top, 1):
        _render_entry(lines, score, branch, desc, when, metrics_json,
                      heading_prefix=f"#{i} — ")
    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def export_history(conn: sqlite3.Connection, output_path: str,
                   limit: int = 50):
    """Export recent evaluation history to a markdown file.

    Shows the most recent evaluations (accepted, rejected, crashed) so that
    agents can see what has been tried and learn from past attempts.
    """
    recent = conn.execute("""
        SELECT score, status, branch, description, evaluated_at, metrics_json
        FROM evaluations ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()

    lines = ["# History", ""]
    for score, status, branch, desc, when, metrics_json in recent:
        _render_entry(lines, score, branch, desc, when, metrics_json,
                      heading_prefix=f"{status} — ")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
