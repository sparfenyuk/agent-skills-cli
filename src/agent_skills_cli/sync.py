from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .config import load_config, save_config
from .errors import ConfigError
from .schema import AgentConfig, RootConfig

_REPO_ID_RE = re.compile(r"[^A-Za-z0-9]+")


def sync_config(config_path: Path, *, force: bool = False) -> None:
    config = load_config(config_path)
    data = config.to_dict()
    project_root = config_path.parent

    store_dir = project_root / config.store_dir
    store_dir.mkdir(parents=True, exist_ok=True)
    agents_root = project_root / ".agent-skills" / "agents"
    agents_root.mkdir(parents=True, exist_ok=True)

    link_context = _LinkContext(
        agents_root=agents_root,
        project_root=project_root,
        agent_targets=config.agents,
        force=force,
    )

    for repo_entry in data.get("repos", []):
        repo_url = repo_entry["repo"]
        rev = repo_entry["rev"]
        repo_id = _repo_id(repo_url)
        repo_root = store_dir / repo_id
        clone_dir = repo_root / "_repo"
        worktrees_root = repo_root / "worktrees"
        worktrees_root.mkdir(parents=True, exist_ok=True)

        _ensure_repo(repo_url, clone_dir)
        _git_fetch(clone_dir)
        resolved_sha = _resolve_rev(clone_dir, rev)
        repo_entry["resolved_sha"] = resolved_sha

        worktree = worktrees_root / resolved_sha
        _ensure_worktree(clone_dir, worktree, resolved_sha)

        for skill in repo_entry.get("skills", []):
            skill_path = worktree / skill["path"]
            if not (skill_path / "SKILL.md").is_file():
                raise ConfigError(
                    f"Missing SKILL.md for {skill['name']} at {skill_path}"
                )
            _link_skill(
                skill_path=skill_path,
                skill_name=skill["name"],
                agents=skill.get("agents", []),
                context=link_context,
            )

    save_config(config_path, RootConfig.from_dict(data))


def _repo_id(repo_url: str) -> str:
    return _REPO_ID_RE.sub("__", repo_url).strip("_")


def _ensure_repo(repo_url: str, clone_dir: Path) -> None:
    if clone_dir.exists():
        return
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", repo_url, str(clone_dir)])


def _git_fetch(clone_dir: Path) -> None:
    _run(["git", "-C", str(clone_dir), "fetch", "--tags", "--prune"])


def _resolve_rev(clone_dir: Path, rev: str) -> str:
    result = _run(
        ["git", "-C", str(clone_dir), "rev-parse", f"{rev}^{{commit}}"],
        capture_output=True,
    )
    return result.stdout.strip()


def _ensure_worktree(clone_dir: Path, worktree: Path, sha: str) -> None:
    if worktree.exists():
        return
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "git",
            "-C",
            str(clone_dir),
            "worktree",
            "add",
            str(worktree),
            sha,
        ]
    )


@dataclass(frozen=True)
class _LinkContext:
    agents_root: Path
    project_root: Path
    agent_targets: dict[str, AgentConfig]
    force: bool


def _link_skill(
    *,
    skill_path: Path,
    skill_name: str,
    agents: Iterable[str],
    context: _LinkContext,
) -> None:
    for agent in agents:
        agent_dir = context.agents_root / agent
        agent_dir.mkdir(parents=True, exist_ok=True)
        _ensure_symlink(agent_dir / skill_name, skill_path, force=context.force)

        target_cfg = context.agent_targets.get(agent)
        if target_cfg and target_cfg.target_dir:
            target_dir = context.project_root / target_cfg.target_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            _ensure_symlink(target_dir / skill_name, skill_path, force=context.force)


def _ensure_symlink(link_path: Path, target: Path, *, force: bool) -> None:
    if link_path.is_symlink():
        if link_path.resolve(strict=False) == target.resolve():
            return
        link_path.unlink()
    elif link_path.exists():
        if not force:
            raise ConfigError(f"Path exists and is not a symlink: {link_path}")
        if link_path.is_dir():
            if any(link_path.iterdir()):
                raise ConfigError(f"Refusing to overwrite non-empty dir: {link_path}")
            link_path.rmdir()
        else:
            link_path.unlink()
    link_path.symlink_to(target, target_is_directory=True)


def _run(
    cmd: list[str], *, capture_output: bool = False
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(  # noqa: S603
            cmd,
            check=True,
            text=True,
            capture_output=capture_output,
        )
    except FileNotFoundError as exc:
        raise ConfigError(f"Command not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        raise ConfigError(f"Command failed: {' '.join(cmd)} ({stderr})") from exc
