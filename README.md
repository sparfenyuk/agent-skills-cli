# Agent Skills Organizer

A tiny CLI to install and enable "agent skills" across projects, with a single
local store and per-agent symlinks. Keep a config in the repo root, run `sync`,
and let the tool do the rest.

## What is a skill?
A skill is a folder containing `SKILL.md` plus optional extras (scripts,
templates, references). This tool installs skills from git repositories and
links them into agent-specific locations for Codex, Claude, and Opencode.

## Features
- Single project store at `.agent-skills/` with reproducible checkouts.
- One config file (`.agent-skills.yaml`) that pins `rev` and tool-resolved SHA.
- Enable skills per agent via symlinks for quick inspection and cleanup.
- Simple CLI with `init`, `install`, `enable`, `sync`, and `update`.

## Requirements
- Python 3.13+
- Git
- A filesystem that supports symlinks

## Install
Install via `uv`:
```bash
uv tool install agent-skills-cli --from git+https://github.com/sparfenyuk/agent-skills-cli.git
agent-skills-cli --help
```

## Quick start
Initialize the config:

```bash
agent-skills-cli init
```

Install a repo and add a skill:

```bash
agent-skills-cli install https://github.com/acme/agent-skills --rev v1.3.0 \
  --skill architecture-feature-mapping-doc --path architecture-feature-mapping-doc \
  --agent codex
```

Sync to fetch and link:

```bash
agent-skills-cli sync
```

## Config file
`.agent-skills.yaml` is the only state file. `resolved_sha` is managed by the
tool after `sync` or `update`.

```yaml
version: 1
store_dir: .agent-skills/store
agents:
  codex:
    target_dir: .codex/skills
  claude:
    target_dir: .claude/skills
  opencode:
    target_dir: .opencode/skills

repos:
  - repo: https://github.com/acme/agent-skills
    rev: v1.3.0
    resolved_sha: 7d2e9a1c8c9d4d3c1a3b2d9f6b2e1a0c0f1d2e3a
    skills:
      - name: architecture-feature-mapping-doc
        path: architecture-feature-mapping-doc
        agents: [codex]
```

## Commands
- `agent-skills-cli init` - Create a default `.agent-skills.yaml`.
- `agent-skills-cli install` - Add a repo and optionally a skill entry.
- `agent-skills-cli enable` - Enable a skill for one or more agents.
- `agent-skills-cli sync` - Fetch repos, resolve SHAs, and create symlinks.
- `agent-skills-cli update` - Re-resolve SHAs and re-sync.
- `agent-skills-cli list` - Show configured repos and skills.

## Design notes
- The store is a local git clone with worktrees per resolved SHA.
- Symlinks live under `.agent-skills/agents/<agent>/` and optionally into each
  agent's configured `target_dir`.
- Missing `SKILL.md` fails `sync` to keep config and store consistent.

## Status
This is an early MVP. Feedback and PRs are welcome.
