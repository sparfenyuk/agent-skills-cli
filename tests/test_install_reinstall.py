from typer.testing import CliRunner

from agent_skills_cli import cli
from agent_skills_cli.config import load_config


def test_install_reinstall_removes_duplicate_repo_entries(monkeypatch, tmp_path):
    config_path = tmp_path / ".agent-skills.yaml"
    config_path.write_text(
        """version: 1
repos:
  - repo: https://example.com/repo
    rev: v1
  - repo: https://example.com/repo
    rev: v2
""",
        encoding="utf-8",
    )

    def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(cli, "sync_repo", _noop)

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "install",
            "https://example.com/repo",
            "--rev",
            "v3",
            "--skill",
            "skill-a",
            "--remote-location",
            "skill-a",
            "--reinstall",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    config = load_config(config_path)
    assert len(config.repos) == 1
    assert config.repos[0].rev == "v3"
    assert config.repos[0].skills[0].name == "skill-a"
