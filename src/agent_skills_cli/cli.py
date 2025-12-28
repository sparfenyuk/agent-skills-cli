from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn, cast

import typer

from .config import init_config, load_config, save_config
from .errors import ConfigError
from .schema import RootConfig
from .sync import sync_config

app = typer.Typer(no_args_is_help=True)

RepoEntry = dict[str, Any]
SkillEntry = dict[str, Any]


def _fail(message: str) -> NoReturn:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _config_path(path: Path | None) -> Path:
    return path or Path(".agent-skills.yaml")


def _save_validated(path: Path, data: dict) -> RootConfig:
    config = RootConfig.from_dict(data)
    save_config(path, config)
    return config


def _ensure_repo_list(data: dict[str, Any]) -> list[RepoEntry]:
    repos_value = data.get("repos")
    if repos_value is None:
        repos_value = []
        data["repos"] = repos_value
    if not isinstance(repos_value, list):
        _fail("repos must be a list")
    for item in repos_value:
        if not isinstance(item, dict):
            _fail("repo entries must be mappings")
    return cast("list[RepoEntry]", repos_value)


def _ensure_skill_list(repo: RepoEntry) -> list[SkillEntry]:
    skills_value = repo.get("skills")
    if skills_value is None:
        skills_value = []
        repo["skills"] = skills_value
    if not isinstance(skills_value, list):
        _fail("skills must be a list")
    for item in skills_value:
        if not isinstance(item, dict):
            _fail("skill entries must be mappings")
    return cast("list[SkillEntry]", skills_value)


@app.command()
def init(
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Path to .agent-skills.yaml"
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config"),
) -> None:
    """Create a default .agent-skills.yaml config."""
    path = _config_path(config)
    try:
        init_config(path, overwrite=force)
    except ConfigError as exc:
        _fail(str(exc))
    typer.echo(f"Initialized {path}")


@app.command("list")
def list_skills(
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Path to .agent-skills.yaml"
    ),
) -> None:
    """List configured repos and skills."""
    path = _config_path(config)
    try:
        cfg = load_config(path)
    except ConfigError as exc:
        _fail(str(exc))

    if not cfg.repos:
        typer.echo("No repos configured.")
        return

    for repo in cfg.repos:
        sha = repo.resolved_sha or "unresolved"
        typer.echo(f"{repo.repo} ({repo.rev}, {sha})")
        if not repo.skills:
            typer.echo("  - no skills")
            continue
        for skill in repo.skills:
            agents = ", ".join(skill.agents) if skill.agents else "unassigned"
            typer.echo(f"  - {skill.name} [{agents}] ({skill.path})")


@app.command()
def install(
    repo: str = typer.Argument(..., help="Git repository URL"),
    rev: str = typer.Option(..., "--rev", help="Git revision (tag/branch/SHA)"),
    skill: str | None = typer.Option(None, "--skill", help="Skill name to add"),
    path: str | None = typer.Option(None, "--path", help="Skill path in the repo"),
    agent: list[str] = typer.Option(
        None, "--agent", "-a", help="Agent to enable for the skill"
    ),
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Path to .agent-skills.yaml"
    ),
) -> None:
    """Add a repo and optionally a skill to the config."""
    config_path = _config_path(config)
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        _fail(str(exc))

    data: dict[str, Any] = cfg.to_dict()
    repos = _ensure_repo_list(data)
    existing = next((item for item in repos if item.get("repo") == repo), None)
    if existing is None:
        existing = {"repo": repo, "rev": rev}
        repos.append(existing)
    elif existing.get("rev") != rev:
        existing["rev"] = rev
        existing.pop("resolved_sha", None)

    if skill or path:
        if not skill or not path:
            _fail("Both --skill and --path are required to add a skill.")
        skills = _ensure_skill_list(existing)
        skills.append(
            {
                "name": skill,
                "path": path,
                "agents": list(agent or []),
            }
        )

    try:
        _save_validated(config_path, data)
    except ConfigError as exc:
        _fail(str(exc))
    typer.echo(f"Updated {config_path}")


@app.command()
def enable(
    skill: str = typer.Argument(..., help="Skill name"),
    agent: list[str] = typer.Option(
        ..., "--agent", "-a", help="Agent to enable for the skill"
    ),
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Path to .agent-skills.yaml"
    ),
) -> None:
    """Enable a skill for one or more agents."""
    config_path = _config_path(config)
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        _fail(str(exc))

    data: dict[str, Any] = cfg.to_dict()
    repos = _ensure_repo_list(data)
    skill_entry = None
    for repo in repos:
        for entry in _ensure_skill_list(repo):
            if entry.get("name") == skill:
                skill_entry = entry
                break
        if skill_entry:
            break

    if skill_entry is None:
        _fail(f"Skill not found: {skill}")

    entry = cast("SkillEntry", skill_entry)
    agents_value = entry.get("agents")
    if agents_value is None:
        agents_value = []
        entry["agents"] = agents_value
    if not isinstance(agents_value, list):
        _fail("Skill agents must be a list")

    agents = cast("list[str]", agents_value)
    for name in agent:
        if name not in agents:
            agents.append(name)

    try:
        _save_validated(config_path, data)
    except ConfigError as exc:
        _fail(str(exc))
    typer.echo(f"Enabled {skill} for {', '.join(agent)}")


@app.command()
def sync(
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Path to .agent-skills.yaml"
    ),
    force: bool = typer.Option(False, "--force", help="Replace mismatched symlinks"),
) -> None:
    """Fetch repos, resolve revisions, and create symlinks."""
    config_path = _config_path(config)
    try:
        sync_config(config_path, force=force)
    except ConfigError as exc:
        _fail(str(exc))
    typer.echo("Sync complete.")


@app.command()
def update(
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Path to .agent-skills.yaml"
    ),
    force: bool = typer.Option(False, "--force", help="Replace mismatched symlinks"),
) -> None:
    """Update resolved SHAs and re-sync."""
    config_path = _config_path(config)
    try:
        sync_config(config_path, force=force)
    except ConfigError as exc:
        _fail(str(exc))
    typer.echo("Update complete.")


def main() -> None:
    app()
