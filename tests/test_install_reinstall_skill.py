from typer.testing import CliRunner

from agent_skills_cli import cli
from agent_skills_cli.config import load_config


def test_install_reinstall_replaces_duplicate_skill(monkeypatch, tmp_path):
    config_path = tmp_path / ".agent-skills.yaml"
    config_path.write_text(
        """version: 1
repos:
  - repo: https://example.com/repo-a
    rev: v1
    skills:
      - name: skill-a
        location: skill-a
  - repo: https://example.com/repo-b
    rev: v1
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
            "https://example.com/repo-b",
            "--rev",
            "v2",
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
    repo_a = next(repo for repo in config.repos if repo.repo.endswith("repo-a"))
    repo_b = next(repo for repo in config.repos if repo.repo.endswith("repo-b"))
    assert not repo_a.skills
    assert repo_b.skills[0].name == "skill-a"
