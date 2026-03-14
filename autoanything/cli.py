from __future__ import annotations

import argparse
from pathlib import Path

from .evaluator import LocalEvaluator
from .models import MetricPattern, ProblemDefinition, ScoreDefinition
from .scaffold import default_ml_metrics, init_challenge, init_local_evaluator


def _metric_patterns(raw_items: list[str]) -> list[MetricPattern]:
    metrics: list[MetricPattern] = []
    for item in raw_items:
        if "=" not in item:
            raise SystemExit(f"Invalid --metric format: {item!r}. Expected name=regex")
        name, regex = item.split("=", 1)
        metrics.append(MetricPattern(name=name, regex=regex))
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoanything", description="AutoAnything challenge toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="scaffold a challenge repo")
    init_parser.add_argument("path", nargs="?", default=".")
    init_parser.add_argument("--name", required=True)
    init_parser.add_argument("--description", required=True)
    init_parser.add_argument("--mutable", action="append", default=[])
    init_parser.add_argument("--readonly", action="append", default=[])
    init_parser.add_argument("--direction", choices=["minimize", "maximize"], required=True)
    init_parser.add_argument("--score-name", required=True)
    init_parser.add_argument("--score-description", default="")
    init_parser.add_argument("--bounded", action="store_true")
    init_parser.add_argument("--bound", type=float)
    init_parser.add_argument("--overwrite", action="store_true")

    evaluator_parser = subparsers.add_parser("evaluator", help="manage a private evaluator")
    evaluator_subparsers = evaluator_parser.add_subparsers(dest="evaluator_command", required=True)

    evaluator_init = evaluator_subparsers.add_parser("init", help="create evaluator/ scaffolding")
    evaluator_init.add_argument("path", nargs="?", default=".")
    evaluator_init.add_argument("--score-command", required=True)
    evaluator_init.add_argument("--score-regex", required=True)
    evaluator_init.add_argument("--metric", action="append", default=[])
    evaluator_init.add_argument("--ml-metrics", action="store_true")
    evaluator_init.add_argument("--base-branch", default="master")
    evaluator_init.add_argument("--proposal-prefix", action="append", default=[])
    evaluator_init.add_argument("--queue-policy", choices=["fifo", "agent_priority"], default="fifo")
    evaluator_init.add_argument("--stale-after-base-commits", type=int)
    evaluator_init.add_argument("--no-fetch-remote", action="store_true")
    evaluator_init.add_argument("--no-commit-public-artifacts", action="store_true")
    evaluator_init.add_argument("--no-push-after-update", action="store_true")
    evaluator_init.add_argument("--overwrite", action="store_true")

    for command in ("score", "once", "loop"):
        sub = evaluator_subparsers.add_parser(command, help=f"run evaluator {command}")
        sub.add_argument("--config", required=True)
        if command == "loop":
            sub.add_argument("--once", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        problem = ProblemDefinition(
            name=args.name,
            description=args.description,
            mutable=args.mutable,
            readonly=args.readonly,
            score=ScoreDefinition(
                direction=args.direction,
                name=args.score_name,
                description=args.score_description,
                bounded=args.bounded,
                bound=args.bound,
            ),
            constraints=[],
        )
        init_challenge(Path(args.path).resolve(), problem, overwrite=args.overwrite)
        return 0

    if args.command == "evaluator" and args.evaluator_command == "init":
        metrics = _metric_patterns(args.metric)
        if args.ml_metrics:
            metrics.extend(default_ml_metrics())
        init_local_evaluator(
            Path(args.path).resolve(),
            score_command=args.score_command,
            score_regex=args.score_regex,
            metrics=metrics,
            base_branch=args.base_branch,
            proposal_prefixes=args.proposal_prefix or ["proposals/"],
            queue_policy=args.queue_policy,
            stale_after_base_commits=args.stale_after_base_commits,
            fetch_remote=not args.no_fetch_remote,
            commit_public_artifacts=not args.no_commit_public_artifacts,
            push_after_update=not args.no_push_after_update,
            overwrite=args.overwrite,
        )
        return 0

    evaluator = LocalEvaluator(Path(args.config).resolve())
    if args.evaluator_command == "score":
        evaluator.evaluate_once()
        return 0
    if args.evaluator_command == "once":
        evaluator.evaluate_once()
        return 0
    if args.evaluator_command == "loop":
        return evaluator.loop(once=args.once)
    return 0
