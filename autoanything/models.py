from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def load_yaml_file(path: Path) -> Any:
    data = yaml.safe_load(path.read_text())
    return {} if data is None else data


def dump_yaml(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)


def _expect_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{context} must be a mapping, got {type(value).__name__}")
    return value


@dataclass(slots=True)
class ScoreDefinition:
    direction: str
    name: str
    description: str = ""
    bounded: bool = False
    bound: float | None = None

    def __post_init__(self) -> None:
        if self.direction not in {"minimize", "maximize"}:
            raise ValueError("score.direction must be 'minimize' or 'maximize'")

    def better(self, candidate: float, incumbent: float | None) -> bool:
        if incumbent is None:
            return True
        if self.direction == "minimize":
            return candidate < incumbent
        return candidate > incumbent

    def leaderboard_reverse(self) -> bool:
        return self.direction == "maximize"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoreDefinition":
        data = _expect_mapping(data, "score")
        return cls(
            direction=str(data["direction"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            bounded=bool(data.get("bounded", False)),
            bound=float(data["bound"]) if data.get("bound") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "direction": self.direction,
            "name": self.name,
            "description": self.description,
            "bounded": self.bounded,
        }
        if self.bound is not None:
            payload["bound"] = self.bound
        return payload


@dataclass(slots=True)
class ProblemDefinition:
    name: str
    description: str
    mutable: list[str]
    readonly: list[str]
    score: ScoreDefinition
    constraints: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemDefinition":
        data = _expect_mapping(data, "problem")
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")).strip(),
            mutable=[str(item) for item in data.get("mutable", [])],
            readonly=[str(item) for item in data.get("readonly", [])],
            score=ScoreDefinition.from_dict(data["score"]),
            constraints=[str(item) for item in data.get("constraints", [])],
        )

    @classmethod
    def from_file(cls, path: Path) -> "ProblemDefinition":
        return cls.from_dict(load_yaml_file(path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "mutable": self.mutable,
            "readonly": self.readonly,
            "score": self.score.to_dict(),
            "constraints": self.constraints,
        }


@dataclass(slots=True)
class MetricPattern:
    name: str
    regex: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricPattern":
        data = _expect_mapping(data, "metric")
        return cls(name=str(data["name"]), regex=str(data["regex"]))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "regex": self.regex}


@dataclass(slots=True)
class EvaluatorConfig:
    config_path: Path
    repo_root: Path
    problem_path: Path
    db_path: Path
    base_branch: str = "master"
    proposal_prefixes: list[str] = field(default_factory=lambda: ["proposals/"])
    queue_policy: str = "fifo"
    stale_after_base_commits: int | None = 20
    rebase_before_score: bool = True
    fetch_remote: bool = True
    commit_public_artifacts: bool = True
    push_after_update: bool = True
    poll_seconds: int = 60
    score_command: str = ""
    score_shell: str = "/bin/bash"
    score_regex: str = r"^score:\s+(?P<value>[-+0-9.eE]+)$"
    metrics: list[MetricPattern] = field(default_factory=list)
    private_log_path: Path = Path("evaluator/last-score.log")
    result_path: Path = Path("evaluator/result.json")
    leaderboard_path: Path = Path("leaderboard.md")
    history_json_path: Path = Path("history/attempts.json")
    dashboard_path: Path = Path("dashboard.html")
    signals_markdown_path: Path = Path("signals.md")
    signals_json_path: Path = Path("signals.json")
    max_recent_failures_for_signal: int = 5

    @classmethod
    def from_file(cls, path: Path) -> "EvaluatorConfig":
        data = _expect_mapping(load_yaml_file(path), "evaluator config")
        repo_root = Path(data.get("repo_root", path.parent.parent)).resolve()

        def resolve(value: str | Path | None, default: str) -> Path:
            raw = Path(value) if value is not None else Path(default)
            if raw.is_absolute():
                return raw
            return (repo_root / raw).resolve()

        metrics = [MetricPattern.from_dict(item) for item in data.get("metrics", [])]
        return cls(
            config_path=path.resolve(),
            repo_root=repo_root,
            problem_path=resolve(data.get("problem_path"), "problem.yaml"),
            db_path=resolve(data.get("db_path"), "evaluator/history.db"),
            base_branch=str(data.get("base_branch", "master")),
            proposal_prefixes=[str(item) for item in data.get("proposal_prefixes", ["proposals/"])],
            queue_policy=str(data.get("queue_policy", "fifo")),
            stale_after_base_commits=(None if data.get("stale_after_base_commits") is None else int(data.get("stale_after_base_commits"))),
            rebase_before_score=bool(data.get("rebase_before_score", True)),
            fetch_remote=bool(data.get("fetch_remote", True)),
            commit_public_artifacts=bool(data.get("commit_public_artifacts", True)),
            push_after_update=bool(data.get("push_after_update", True)),
            poll_seconds=int(data.get("poll_seconds", 60)),
            score_command=str(data["score_command"]),
            score_shell=str(data.get("score_shell", "/bin/bash")),
            score_regex=str(data.get("score_regex", r"^score:\s+(?P<value>[-+0-9.eE]+)$")),
            metrics=metrics,
            private_log_path=resolve(data.get("private_log_path"), "evaluator/last-score.log"),
            result_path=resolve(data.get("result_path"), "evaluator/result.json"),
            leaderboard_path=resolve(data.get("leaderboard_path"), "leaderboard.md"),
            history_json_path=resolve(data.get("history_json_path"), "history/attempts.json"),
            dashboard_path=resolve(data.get("dashboard_path"), "dashboard.html"),
            signals_markdown_path=resolve(data.get("signals_markdown_path"), "signals.md"),
            signals_json_path=resolve(data.get("signals_json_path"), "signals.json"),
            max_recent_failures_for_signal=int(data.get("max_recent_failures_for_signal", 5)),
        )

    def to_dict(self) -> dict[str, Any]:
        def rel(path: Path) -> str:
            try:
                return path.relative_to(self.repo_root).as_posix()
            except ValueError:
                return path.as_posix()

        return {
            "repo_root": self.repo_root.as_posix(),
            "problem_path": rel(self.problem_path),
            "db_path": rel(self.db_path),
            "base_branch": self.base_branch,
            "proposal_prefixes": self.proposal_prefixes,
            "queue_policy": self.queue_policy,
            "stale_after_base_commits": self.stale_after_base_commits,
            "rebase_before_score": self.rebase_before_score,
            "fetch_remote": self.fetch_remote,
            "commit_public_artifacts": self.commit_public_artifacts,
            "push_after_update": self.push_after_update,
            "poll_seconds": self.poll_seconds,
            "score_command": self.score_command,
            "score_shell": self.score_shell,
            "score_regex": self.score_regex,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "private_log_path": rel(self.private_log_path),
            "result_path": rel(self.result_path),
            "leaderboard_path": rel(self.leaderboard_path),
            "history_json_path": rel(self.history_json_path),
            "dashboard_path": rel(self.dashboard_path),
            "signals_markdown_path": rel(self.signals_markdown_path),
            "signals_json_path": rel(self.signals_json_path),
            "max_recent_failures_for_signal": self.max_recent_failures_for_signal,
        }
