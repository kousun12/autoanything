"""AutoAnything challenge and evaluator toolkit."""

from .models import EvaluatorConfig, ProblemDefinition, ScoreDefinition
from .evaluator import LocalEvaluator
from .scaffold import init_challenge, init_local_evaluator

__all__ = [
    "EvaluatorConfig",
    "LocalEvaluator",
    "ProblemDefinition",
    "ScoreDefinition",
    "init_challenge",
    "init_local_evaluator",
]
