import pytest

from agent_skills_cli.config import init_config, load_config
from agent_skills_cli.errors import ConfigError


def test_init_creates_default(tmp_path):
    path = tmp_path / ".agent-skills.yaml"
    init_config(path)
    config = load_config(path)
    assert config.version == 1
    assert "codex" in config.agents
    assert config.agents["codex"].target_dir == ".codex/skills"


def test_init_requires_overwrite_flag(tmp_path):
    path = tmp_path / ".agent-skills.yaml"
    init_config(path)
    with pytest.raises(ConfigError):
        init_config(path)
