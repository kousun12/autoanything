#!/usr/bin/env python3
"""
Generate a progress chart from an evaluation history database.

Produces a chart matching the progress.png style: gray dots for discarded,
green dots for kept, step line for running best, italic labels.

Usage:
    python test_problems/plot_progress.py evaluator/history.db
    python test_problems/plot_progress.py evaluator/history.db -o chart.png
    python test_problems/plot_progress.py path/to/history.db --title "My Run"
"""

import argparse
import os
import sqlite3
import sys


def generate_chart(db_path, output_path, title=None, direction="minimize",
                   score_label="Score"):
    """Generate a progress chart from a history database.

    Args:
        db_path: Path to SQLite history.db (must have an `evaluations` table).
        output_path: Where to save the PNG.
        title: Custom chart title (auto-generated if None).
        direction: "minimize" or "maximize".
        score_label: Y-axis label for the metric.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib required: pip install matplotlib", file=sys.stderr)
        sys.exit(1)

    # Load data
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, score, status, description FROM evaluations ORDER BY id"
    ).fetchall()
    conn.close()

    if not rows:
        print("No evaluations found in database.", file=sys.stderr)
        sys.exit(1)

    # Classify points
    kept_x, kept_y, kept_labels = [], [], []
    disc_x, disc_y = [], []

    for i, (_, score, status, desc) in enumerate(rows):
        if status in ("accepted", "baseline"):
            kept_x.append(i)
            kept_y.append(score)
            kept_labels.append(desc or "")
        elif score is not None:
            disc_x.append(i)
            disc_y.append(score)

    # Build step-line coordinates for running best
    step_x, step_y = [], []
    running = None
    for i, (_, score, status, _) in enumerate(rows):
        if status in ("accepted", "baseline"):
            if running is not None:
                # Horizontal extension to current x at previous best
                step_x.append(i)
                step_y.append(running)
            running = score
            step_x.append(i)
            step_y.append(running)
    # Extend to end of chart
    if running is not None and len(rows) > 1:
        step_x.append(len(rows) - 1)
        step_y.append(running)

    # ---- Plot ----
    fig, ax = plt.subplots(figsize=(14, 6))

    # Discarded (gray dots)
    ax.scatter(disc_x, disc_y, c="#C0C0C0", s=28, alpha=0.45,
               label="Discarded", zorder=2, linewidths=0)

    # Running best (step line)
    if step_x:
        ax.plot(step_x, step_y, color="#66BB6A", linewidth=2, alpha=0.7,
                label="Running best", zorder=3)

    # Kept (green dots)
    ax.scatter(kept_x, kept_y, c="#43A047", s=55, alpha=0.9,
               label="Kept", zorder=4, edgecolors="white", linewidths=0.5)

    # Italic labels on kept points
    for x, y, label in zip(kept_x, kept_y, kept_labels):
        if label:
            short = (label[:35] + "\u2026") if len(label) > 38 else label
            ax.annotate(
                short, (x, y),
                textcoords="offset points", xytext=(5, 8),
                fontsize=7.5, fontstyle="italic", color="#43A047",
                rotation=30, ha="left", va="bottom",
            )

    # Axes
    dir_str = "lower is better" if direction == "minimize" else "higher is better"
    ax.set_xlabel("Experiment #", fontsize=12)
    ax.set_ylabel(f"{score_label} ({dir_str})", fontsize=12)

    # Title
    n_total = len(rows)
    n_kept = sum(1 for r in rows if r[2] == "accepted")
    if title is None:
        title = (f"AutoAnything Progress: {n_total} Experiments, "
                 f"{n_kept} Kept Improvement{'s' if n_kept != 1 else ''}")
    ax.set_title(title, fontsize=14)

    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description="Generate progress chart from evaluation history"
    )
    parser.add_argument("db_path", help="Path to history.db")
    parser.add_argument("-o", "--output", default=None,
                        help="Output PNG path (default: <db_dir>/progress.png)")
    parser.add_argument("--title", default=None, help="Custom chart title")
    parser.add_argument("--direction", default="minimize",
                        choices=["minimize", "maximize"])
    parser.add_argument("--score-label", default="Score",
                        help="Y-axis label (default: Score)")
    args = parser.parse_args()

    output = args.output or os.path.join(
        os.path.dirname(args.db_path) or ".", "progress.png"
    )
    generate_chart(args.db_path, output, args.title, args.direction,
                   args.score_label)
    print(f"Chart saved to {output}")


if __name__ == "__main__":
    main()
