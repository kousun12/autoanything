from __future__ import annotations

import argparse
from pathlib import Path

from autoanything.evaluator import run_evaluation_loop
from autoanything.scaffold import build_challenge_from_args, build_evaluator_from_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoanything", description="Scaffold and operate AutoAnything challenge repos.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Scaffold a public challenge repo.")
    init_parser.add_argument("--path", default=".", help="Where to create the challenge.")
    init_parser.add_argument("--name", help="Challenge name.")
    init_parser.add_argument("--description", help="Challenge description.")
    init_parser.add_argument("--mutable", action="append", help="Mutable file path. Repeat for multiple entries.")
    init_parser.add_argument("--readonly", action="append", help="Read-only file path. Repeat for multiple entries.")
    init_parser.add_argument("--score-direction", choices=["minimize", "maximize"], default="minimize")
    init_parser.add_argument("--score-name", help="Public name of the score.")
    init_parser.add_argument("--score-description", help="Public description of the score.")
    init_parser.add_argument("--bounded", help="Whether the score has a known bound (true/false).")
    init_parser.add_argument("--score-bound", type=float, help="Optional known best bound.")
    init_parser.add_argument("--constraint", action="append", help="Constraint text. Repeat for multiple entries.")
    init_parser.add_argument("--base-branch", default="master", help="Default branch the evaluator promotes into.")
    init_parser.add_argument("--overwrite", action="store_true", help="Overwrite files created by the scaffold.")
    init_parser.set_defaults(handler=handle_init)

    evaluator_parser = subparsers.add_parser("evaluator", help="Scaffold or run the private evaluator.")
    evaluator_subparsers = evaluator_parser.add_subparsers(dest="evaluator_command", required=True)

    evaluator_init = evaluator_subparsers.add_parser("init", help="Create a gitignored local evaluator.")
    evaluator_init.add_argument("--repo-root", default=".", help="Challenge repo root.")
    evaluator_init.add_argument("--score-command", help="Command that scores a checked-out proposal.")
    evaluator_init.add_argument("--score-regex", help="Regex with one numeric capture group.")
    evaluator_init.add_argument("--direction", choices=["minimize", "maximize"], default="minimize")
    evaluator_init.add_argument("--base-branch", default="master")
    evaluator_init.add_argument("--proposal-prefix", default="proposals/")
    evaluator_init.add_argument("--leaderboard", default="leaderboard.md")
    evaluator_init.add_argument("--overwrite", action="store_true")
    evaluator_init.set_defaults(handler=handle_evaluator_init)

    internal_eval = subparsers.add_parser("internal-evaluate", help=argparse.SUPPRESS)
    internal_eval.add_argument("--repo-root", required=True)
    internal_eval.add_argument("--base-branch", required=True)
    internal_eval.add_argument("--proposal-prefix", default="proposals/")
    internal_eval.add_argument("--direction", choices=["minimize", "maximize"], required=True)
    internal_eval.add_argument("--score-script", required=True)
    internal_eval.add_argument("--database", required=True)
    internal_eval.add_argument("--leaderboard", required=True)
    internal_eval.add_argument("--remote-name", default="origin")
    internal_eval.add_argument("--once", action="store_true")
    internal_eval.add_argument("--sleep-seconds", type=float, default=15.0)
    internal_eval.set_defaults(handler=handle_internal_evaluate)

    return parser


def handle_init(args: argparse.Namespace) -> int:
    build_challenge_from_args(args)
    return 0


def handle_evaluator_init(args: argparse.Namespace) -> int:
    build_evaluator_from_args(args)
    return 0


def handle_internal_evaluate(args: argparse.Namespace) -> int:
    return run_evaluation_loop(
        repo_root=Path(args.repo_root).resolve(),
        base_branch=args.base_branch,
        proposal_prefix=args.proposal_prefix,
        direction=args.direction,
        score_script=Path(args.score_script).resolve(),
        database_path=Path(args.database).resolve(),
        leaderboard_path=Path(args.leaderboard).resolve(),
        remote_name=args.remote_name,
        once=args.once,
        sleep_seconds=args.sleep_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
