from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePath

from .errors import ConfigError

_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_AGENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _require_str(data: dict, key: str) -> str:
    if key not in data:
        raise ConfigError(f"Missing required key: {key}")
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Expected non-empty string for '{key}'")
    return value


def _optional_str(data: dict, key: str, default: str | None = None) -> str | None:
    if key not in data:
        return default
    value = data[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Expected non-empty string for '{key}'")
    return value


def _optional_list(data: dict, key: str, default: list | None = None) -> list:
    if key not in data:
        return default if default is not None else []
    value = data[key]
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"Expected list for '{key}'")
    return value


def _optional_dict(data: dict, key: str, default: dict | None = None) -> dict:
    if key not in data:
        return default if default is not None else {}
    value = data[key]
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Expected mapping for '{key}'")
    return value


def _expect_int(data: dict, key: str) -> int:
    if key not in data:
        raise ConfigError(f"Missing required key: {key}")
    value = data[key]
    if not isinstance(value, int):
        raise ConfigError(f"Expected integer for '{key}'")
    return value


def _validate_relpath(path: str, key: str) -> None:
    if not path.strip():
        raise ConfigError(f"Expected non-empty string for '{key}'")
    if path.startswith(("/", "\\")):
        raise ConfigError(f"Path must be relative for '{key}'")
    candidate = PurePath(path)
    if candidate.is_absolute():
        raise ConfigError(f"Path must be relative for '{key}'")
    if candidate.parts:
        first = candidate.parts[0]
        if re.fullmatch(r"[A-Za-z]:", first):
            raise ConfigError(f"Path must be relative for '{key}'")
    if ".." in candidate.parts:
        raise ConfigError(f"Path cannot contain '..' for '{key}'")


def _validate_unique(items: Iterable[str], label: str) -> None:
    seen = set()
    for item in items:
        if item in seen:
            raise ConfigError(f"Duplicate {label}: {item}")
        seen.add(item)


@dataclass(frozen=True)
class AgentConfig:
    target_dir: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> AgentConfig:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ConfigError("Agent config must be a mapping")
        target_dir = _optional_str(data, "target_dir")
        if target_dir:
            _validate_relpath(target_dir, "target_dir")
        return cls(target_dir=target_dir)

    def to_dict(self) -> dict:
        data: dict = {}
        if self.target_dir:
            data["target_dir"] = self.target_dir
        return data


@dataclass(frozen=True)
class SkillConfig:
    name: str
    path: str
    agents: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> SkillConfig:
        if not isinstance(data, dict):
            raise ConfigError("Skill config must be a mapping")
        name = _require_str(data, "name")
        path = _require_str(data, "path")
        agents = _optional_list(data, "agents", [])
        if not all(isinstance(a, str) and a.strip() for a in agents):
            raise ConfigError("Skill agents must be non-empty strings")
        return cls(name=name, path=path, agents=agents)

    def validate(self) -> None:
        _validate_relpath(self.path, "skills[].path")
        _validate_unique(self.agents, f"agent in skill '{self.name}'")

    def to_dict(self) -> dict:
        data: dict[str, object] = {
            "name": self.name,
            "path": self.path,
        }
        if self.agents:
            data["agents"] = list(self.agents)
        return data


@dataclass(frozen=True)
class RepoConfig:
    repo: str
    rev: str
    resolved_sha: str | None = None
    skills: list[SkillConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> RepoConfig:
        if not isinstance(data, dict):
            raise ConfigError("Repo config must be a mapping")
        repo = _require_str(data, "repo")
        rev = _require_str(data, "rev")
        resolved_sha = _optional_str(data, "resolved_sha")
        skills = [
            SkillConfig.from_dict(raw) for raw in _optional_list(data, "skills", [])
        ]
        return cls(repo=repo, rev=rev, resolved_sha=resolved_sha, skills=skills)

    def validate(self) -> None:
        if self.resolved_sha and not _SHA_RE.fullmatch(self.resolved_sha):
            raise ConfigError(
                f"resolved_sha must be a 7-40 char hex string: {self.resolved_sha}"
            )
        _validate_unique((skill.name for skill in self.skills), "skill name")
        for skill in self.skills:
            skill.validate()

    def to_dict(self) -> dict:
        data: dict[str, object] = {
            "repo": self.repo,
            "rev": self.rev,
        }
        if self.resolved_sha:
            data["resolved_sha"] = self.resolved_sha
        if self.skills:
            data["skills"] = [skill.to_dict() for skill in self.skills]
        return data


@dataclass(frozen=True)
class RootConfig:
    version: int
    store_dir: str = ".agent-skills/store"
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    repos: list[RepoConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> RootConfig:
        version = _expect_int(data, "version")
        store_dir = _optional_str(data, "store_dir", ".agent-skills/store")
        if store_dir is None:
            store_dir = ".agent-skills/store"
        _validate_relpath(store_dir, "store_dir")

        raw_agents = _optional_dict(data, "agents", {})
        agents: dict[str, AgentConfig] = {}
        for name, cfg in raw_agents.items():
            if not isinstance(name, str) or not name.strip():
                raise ConfigError("Agent names must be non-empty strings")
            if not _AGENT_NAME_RE.fullmatch(name):
                raise ConfigError(f"Invalid agent name: {name}")
            agents[name] = AgentConfig.from_dict(cfg)

        repos = [RepoConfig.from_dict(raw) for raw in _optional_list(data, "repos", [])]

        config = cls(version=version, store_dir=store_dir, agents=agents, repos=repos)
        config.validate()
        return config

    def validate(self) -> None:
        if self.version != 1:
            raise ConfigError("Unsupported config version (expected 1)")
        if not self.store_dir.strip():
            raise ConfigError("store_dir must be a non-empty string")

        _validate_unique((repo.repo for repo in self.repos), "repo URL")

        skill_names: list[str] = []
        for repo in self.repos:
            repo.validate()
            skill_names.extend(skill.name for skill in repo.skills)
        _validate_unique(skill_names, "skill name")

    def to_dict(self) -> dict:
        data = {
            "version": self.version,
            "store_dir": self.store_dir,
        }
        if self.agents:
            data["agents"] = {name: cfg.to_dict() for name, cfg in self.agents.items()}
        if self.repos:
            data["repos"] = [repo.to_dict() for repo in self.repos]
        return data
