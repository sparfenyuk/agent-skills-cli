# Agent Skills Manager - System Design (Python)

## Goals
- Provide a single project-local store for all skills under `.agent-skills/`.
- Install skills from git repositories and enable them per agent (codex/claude/opencode).
- Track versions in one config file using `rev` and tool-managed `resolved_sha`.
- Keep the workflow similar to `pre-commit` (config in repo root, sync to apply).

## Non-goals
- Running skills or enforcing their runtime behavior.
- Supporting non-git sources beyond local paths and HTTP(S) git URLs.

## Concepts
- **Skill**: A directory containing `SKILL.md` and optional extras.
- **Repo**: A git repository that can contain one or many skills.
- **Store**: A local cache of repos checked out at pinned revisions.
- **Agent links**: Symlinks for each agent pointing at store locations.

## On-disk layout
```
project/
  .agent-skills.yaml
  .agent-skills/
    store/
      <repo_id>/<resolved_sha>/...
    agents/
      codex/
      claude/
      opencode/
```

## Config file
`.agent-skills.yaml` is the only state file. The tool updates `resolved_sha` in place.

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
        location: architecture-feature-mapping-doc
        agents: [codex]
      - name: skill-installer
        location: .system/skill-installer
        agents: [codex, claude]
```

Notes:
- `resolved_sha` is tool-managed and may be absent before the first `sync`.
- `repo_id` is derived from `repo` (e.g., `github.com__acme__agent-skills`).
- `agents[].target_dir` is optional. If set, symlinks are created there too.

## CLI commands (minimal)
```
agent-skills init
agent-skills-cli install <repo> --rev v1.2.3 [--skill name] [--remote-location location]
agent-skills enable <skill> --agent codex
agent-skills sync
agent-skills update [--repo ...] [--skill ...]
agent-skills list
```

## Behavior

### init
- Create `.agent-skills.yaml` with defaults.
- Create `.agent-skills/agents/` and `.agent-skills/store/`.

### install
- Add repo entry to config (with `rev`).
- Add skill entry with `location` and `name`.
- Does not clone until `sync` unless `--sync` is provided.

### enable
- Adds or updates `agents` list for a skill.
- Creates symlinks on `sync`.

### sync
- For each repo:
  - Clone or fetch into `.agent-skills/store/<repo_id>/`.
  - Resolve `rev` to a commit SHA and write `resolved_sha` to config.
  - Check out to `.agent-skills/store/<repo_id>/<resolved_sha>/`.
  - Validate each `skills[].location` contains `SKILL.md`.
- For each agent:
  - Create symlinks in `.agent-skills/agents/<agent>/<skill_name>`.
  - If `agents[].target_dir` is set, also link there.

### update
- Fetch remote for each repo or a specific one.
- Re-resolve `rev` to new SHA and update `resolved_sha`.
- Run `sync` to refresh store and symlinks.

## Validation rules
- A skill location must exist and contain `SKILL.md`.
- Symlink name defaults to `skills[].name`; collisions are errors unless `--force`.
- Only locations inside the repo are allowed.

## Python module layout (proposed)
```
agent_skills/
  cli.py                # argparse entrypoint
  config.py             # load/save .agent-skills.yaml
  repo.py               # git clone/fetch/resolve
  store.py              # store paths, checkout logic
  skills.py             # validate SKILL.md, skill metadata
  links.py              # symlink creation and cleanup
  agents.py             # agent target dir conventions
  errors.py             # typed exceptions
```

## Key design choices
- Single config file to keep state simple and human-editable.
- Tool-managed `resolved_sha` enables reproducibility without a lock file.
- Symlinks under `.agent-skills/agents/` allow easy inspection and cleanup.
