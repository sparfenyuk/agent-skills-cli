from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import load_config, save_config
from .errors import ConfigError
from .schema import AgentConfig, RootConfig

_REPO_ID_RE = re.compile(r"[^A-Za-z0-9]+")


def sync_config(
    config_path: Path, *, force: bool = False, verbose: bool = False
) -> None:
    _sync_config(config_path, force=force, repo_filter=None, verbose=verbose)


def sync_repo(
    config_path: Path, repo_url: str, *, force: bool = False, verbose: bool = False
) -> None:
    _sync_config(config_path, force=force, repo_filter={repo_url}, verbose=verbose)


def _sync_config(
    config_path: Path, *, force: bool, repo_filter: set[str] | None, verbose: bool
) -> None:
    config = load_config(config_path)
    data = config.to_dict()
    project_root = config_path.parent
    store_dir = project_root / config.store_dir
    store_dir.mkdir(parents=True, exist_ok=True)
    link_context = _LinkContext(
        project_root=project_root,
        agent_targets=config.agents,
        force=force,
    )
    log = _logger(enabled=verbose)
    log(f"Sync start: {config_path}")
    log(f"Store dir: {store_dir}")

    created_dirs: list[Path] = []
    processed_repos: dict[Path, str] = {}

    def _sync_body() -> None:
        for repo_entry in data.get("repos", []):
            if repo_filter is not None and repo_entry.get("repo") not in repo_filter:
                continue
            repo_url = repo_entry["repo"]
            rev = repo_entry["rev"]
            log(f"Repo: {repo_url} ({rev})")
            sparse_paths = _collect_sparse_paths(repo_entry)
            if not sparse_paths:
                log("No skill paths configured, skipping.")
                continue
            log(f"Sparse paths: {', '.join(sparse_paths)}")
            repo_id = _repo_id(repo_url)
            repo_root = store_dir / repo_id
            resolved_sha, created = _export_sparse_repo(
                repo_url=repo_url,
                rev=rev,
                repo_root=repo_root,
                sparse_paths=sparse_paths,
                log=log,
            )
            repo_entry["resolved_sha"] = resolved_sha
            log(f"Resolved SHA: {resolved_sha}")
            if created:
                created_dirs.append(repo_root / resolved_sha)
            processed_repos[repo_root] = resolved_sha

            worktree = repo_root / resolved_sha
            for skill in repo_entry.get("skills", []):
                skill_root = _normalize_skill_path(skill.get("location", ""))
                skill_path = worktree / skill_root
                log(f"Checking skill {skill['name']} at {skill_path}")
                if not (skill_path / "SKILL.md").is_file():
                    raise ConfigError(
                        f"Missing SKILL.md for {skill['name']} at {skill_path}"
                    )
                _link_skill(
                    skill_path=skill_path,
                    skill_name=skill["name"],
                    agents=skill.get("agents", []),
                    context=link_context,
                    log=log,
                )

        _cleanup_store(
            store_dir=store_dir,
            processed_repos=processed_repos,
            repo_filter=repo_filter,
            log=log,
        )
        save_config(config_path, RootConfig.from_dict(data))
        log("Sync complete.")

    try:
        _sync_body()
    except Exception:
        for created_dir in created_dirs:
            if created_dir.exists():
                log(f"Cleaning store dir: {created_dir}")
                shutil.rmtree(created_dir)
        raise


def _repo_id(repo_url: str) -> str:
    return _REPO_ID_RE.sub("__", repo_url).strip("_")


def _collect_sparse_paths(repo_entry: dict) -> list[str]:
    patterns: list[str] = []
    for skill in repo_entry.get("skills", []):
        path = _normalize_skill_path(skill.get("location", ""))
        if not path:
            continue
        prefix = path.rstrip("/")
        base = "" if prefix in {"", "."} else f"{prefix}/"
        patterns.extend(
            [
                f"{base}SKILL.md",
                f"{base}references/**",
                f"{base}scripts/**",
            ]
        )
    return _dedupe(patterns)


def _normalize_skill_path(value: object) -> str:
    raw = str(value).strip()
    if not raw:
        return ""
    cleaned = raw.rstrip("/")
    if cleaned.lower().endswith("skill.md"):
        parent = PurePosixPath(cleaned).parent
        cleaned = "" if str(parent) == "." else str(parent)
    return cleaned


def _export_sparse_repo(
    *,
    repo_url: str,
    rev: str,
    repo_root: Path,
    sparse_paths: list[str],
    log: Callable[[str], None],
) -> tuple[str, bool]:
    repo_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        log(f"Init temp repo: {tmp_path}")
        log(f"Git sparse checkout setup: {', '.join(sparse_paths)}")
        _run(["git", "init", str(tmp_path)])
        _run(["git", "-C", str(tmp_path), "remote", "add", "origin", repo_url])
        _run(["git", "-C", str(tmp_path), "sparse-checkout", "init", "--no-cone"])
        _run(
            [
                "git",
                "-C",
                str(tmp_path),
                "sparse-checkout",
                "set",
                "--no-cone",
                *sparse_paths,
            ]
        )
        log(f"Fetch depth=1 {rev}")
        _run(
            [
                "git",
                "-C",
                str(tmp_path),
                "fetch",
                "--depth",
                "1",
                "origin",
                rev,
            ]
        )
        log("Checkout FETCH_HEAD")
        _run(["git", "-C", str(tmp_path), "checkout", "FETCH_HEAD"])
        resolved_sha = str(
            _run(
                ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                capture_output=True,
            ).stdout.strip()
        )

        dest = repo_root / resolved_sha
        if dest.exists():
            log(f"Export exists: {dest}")
            return resolved_sha, False

        temp_export = repo_root / f".tmp-{resolved_sha}"
        if temp_export.exists():
            shutil.rmtree(temp_export)
        log(f"Export to {temp_export}")
        try:
            _copy_tree(tmp_path, temp_export)
            temp_export.replace(dest)
        finally:
            if temp_export.exists():
                shutil.rmtree(temp_export)
        return resolved_sha, True


@dataclass(frozen=True)
class _LinkContext:
    project_root: Path
    agent_targets: dict[str, AgentConfig]
    force: bool


def _link_skill(
    *,
    skill_path: Path,
    skill_name: str,
    agents: Iterable[str],
    context: _LinkContext,
    log: Callable[[str], None],
) -> None:
    for agent in agents:
        target_cfg = context.agent_targets.get(agent)
        if target_cfg and target_cfg.target_dir:
            target_dir = context.project_root / target_cfg.target_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            _ensure_symlink(target_dir / skill_name, skill_path, force=context.force)
            log(f"Linked {skill_name} -> {target_dir / skill_name}")
        else:
            log(f"Skipped {skill_name} for {agent}: no target_dir configured")


def _ensure_symlink(link_path: Path, target: Path, *, force: bool) -> None:
    if not target.exists():
        raise ConfigError(f"Symlink target does not exist: {target}")
    if not target.is_dir():
        raise ConfigError(f"Symlink target is not a directory: {target}")
    resolved_target = target.resolve()
    if link_path.is_symlink():
        if link_path.resolve(strict=False) == resolved_target:
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
    link_path.symlink_to(resolved_target, target_is_directory=True)


def _copy_tree(src: Path, dest: Path) -> None:
    def _ignore(_: str, entries: list[str]) -> set[str]:
        return {".git"} if ".git" in entries else set()

    shutil.copytree(src, dest, ignore=_ignore)


def _cleanup_store(
    *,
    store_dir: Path,
    processed_repos: dict[Path, str],
    repo_filter: set[str] | None,
    log: Callable[[str], None],
) -> None:
    for repo_root, keep_sha in processed_repos.items():
        _cleanup_repo_root(repo_root=repo_root, keep={keep_sha}, log=log)

    if repo_filter is not None:
        return

    keep_roots = set(processed_repos.keys())
    for entry in store_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry in keep_roots:
            continue
        log(f"Pruning store repo: {entry}")
        shutil.rmtree(entry)


def _cleanup_repo_root(
    *, repo_root: Path, keep: set[str], log: Callable[[str], None]
) -> None:
    if not repo_root.exists():
        return
    for entry in repo_root.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        if name in keep:
            continue
        if name.startswith(".tmp-"):
            log(f"Removing temp export: {entry}")
            shutil.rmtree(entry)
            continue
        log(f"Pruning store revision: {entry}")
        shutil.rmtree(entry)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _logger(*, enabled: bool) -> Callable[[str], None]:
    logger = logging.getLogger("agent_skills_cli.sync")

    def _log(message: str) -> None:
        if enabled:
            logger.info(message)

    return _log


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
