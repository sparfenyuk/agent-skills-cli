import pytest

from agent_skills_cli.errors import ConfigError
from agent_skills_cli.schema import RootConfig


def test_requires_version():
    with pytest.raises(ConfigError):
        RootConfig.from_dict({})


def test_store_dir_must_be_relative():
    with pytest.raises(ConfigError):
        RootConfig.from_dict({"version": 1, "store_dir": "/abs/path"})


def test_invalid_agent_name():
    with pytest.raises(ConfigError):
        RootConfig.from_dict({"version": 1, "agents": {"bad name": {}}})


def test_duplicate_repo_urls():
    config = {
        "version": 1,
        "repos": [
            {"repo": "https://example.com/repo", "rev": "v1"},
            {"repo": "https://example.com/repo", "rev": "v2"},
        ],
    }
    with pytest.raises(ConfigError):
        RootConfig.from_dict(config)


def test_duplicate_skill_names_across_repos():
    config = {
        "version": 1,
        "repos": [
            {
                "repo": "https://example.com/repo1",
                "rev": "v1",
                "skills": [{"name": "skill-a", "location": "skills/a"}],
            },
            {
                "repo": "https://example.com/repo2",
                "rev": "v1",
                "skills": [{"name": "skill-a", "location": "skills/a"}],
            },
        ],
    }
    with pytest.raises(ConfigError):
        RootConfig.from_dict(config)


def test_skill_path_cannot_escape():
    config = {
        "version": 1,
        "repos": [
            {
                "repo": "https://example.com/repo",
                "rev": "v1",
                "skills": [{"name": "skill-a", "location": "../bad"}],
            }
        ],
    }
    with pytest.raises(ConfigError):
        RootConfig.from_dict(config)


def test_resolved_sha_format():
    config = {
        "version": 1,
        "repos": [
            {
                "repo": "https://example.com/repo",
                "rev": "v1",
                "resolved_sha": "not-a-sha",
            }
        ],
    }
    with pytest.raises(ConfigError):
        RootConfig.from_dict(config)


def test_duplicate_skill_agents():
    config = {
        "version": 1,
        "repos": [
            {
                "repo": "https://example.com/repo",
                "rev": "v1",
                "skills": [
                    {
                        "name": "skill-a",
                        "location": "skill-a",
                        "agents": ["codex", "codex"],
                    }
                ],
            }
        ],
    }
    with pytest.raises(ConfigError):
        RootConfig.from_dict(config)
