from __future__ import annotations

from pathlib import Path

from .errors import ConfigError
from .schema import AgentConfig, RootConfig

PathLike = Path | str


def default_config() -> RootConfig:
    return RootConfig(
        version=1,
        store_dir=".agent-skills/store",
        agents={
            "codex": AgentConfig(target_dir=".codex/skills"),
            "claude": AgentConfig(target_dir=".claude/skills"),
            "opencode": AgentConfig(target_dir=".opencode/skills"),
        },
        repos=[],
    )


def init_config(path: PathLike, *, overwrite: bool = False) -> RootConfig:
    target = Path(path)
    if target.exists() and not overwrite:
        raise ConfigError(f"Config file already exists: {target}")
    config = default_config()
    save_config(target, config)
    return config


def load_config(path: PathLike) -> RootConfig:
    raw = _load_yaml(Path(path))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("Config must be a YAML mapping at the top level")
    return RootConfig.from_dict(raw)


def save_config(path: PathLike, config: RootConfig) -> None:
    _dump_yaml(Path(path), config.to_dict())


def _load_yaml(path: Path) -> object:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required to load config files") from exc
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _dump_yaml(path: Path, data: dict) -> None:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required to save config files") from exc
    content = yaml.safe_dump(data, sort_keys=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(content)
