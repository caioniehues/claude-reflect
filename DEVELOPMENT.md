# Local Development

How to install `claude-reflect` locally and iterate on it.

There are two ways to run the plugin locally. They serve different purposes — pick
based on whether you want to **edit** the code or just **use** a pinned copy.

| Goal | Method | Edits take effect? |
|------|--------|--------------------|
| Develop / edit the plugin | `--plugin-dir` (see below) | Yes, after `/reload-plugins` |
| Use a stable local copy | `/plugin install` from the local marketplace | No — installs a frozen copy |

## Development workflow (edit + reload)

Use this while working on the plugin. It loads the plugin **directly from this
repo** — no copy — so your edits are live.

```bash
# From the repo root:
./scripts/dev.sh

# ...which is just:
claude --plugin-dir "$(pwd)"
```

Then, after editing any script, command, hook, or skill:

```
/reload-plugins
```

`/reload-plugins` reloads plugins, skills, agents, hooks, and plugin MCP/LSP
servers **without restarting the session**. No reinstall needed.

What hot-reloads on `/reload-plugins`:
- Commands — `commands/*.md`
- Skills — `skills/<name>/SKILL.md`
- Hooks — `hooks/hooks.json` and the scripts it points at
- Agents / MCP / LSP definitions

> Note: a hook *fires* the script fresh on every event, so Python changes under
> `scripts/` are picked up on the next hook invocation even without a reload. Run
> `/reload-plugins` when you change **hook wiring** (`hooks/hooks.json`), commands,
> or skills.

## Install workflow (frozen copy)

Use this to run a stable copy, or to verify the plugin behaves as it will for end
users. This repo is its own single-plugin marketplace
(`.claude-plugin/marketplace.json`).

```
/plugin marketplace add /home/caio/Projects/claude-reflect
/plugin install claude-reflect@claude-reflect-marketplace
```

**Caveat:** `/plugin install` **copies** the plugin into
`~/.claude/plugins/cache/`. Editing this repo afterwards does **not** change the
installed copy. To pick up repo changes you must reinstall — or just use
`--plugin-dir` above for development.

## Testing

```bash
# Run the test suite
python -m pytest tests/ -v

# Exercise the capture hook directly with simulated input
echo '{"prompt":"no, use gpt-5.1 not gpt-5"}' | python3 scripts/capture_learning.py

# Inspect / reset the learnings queue
cat ~/.claude/learnings-queue.json
echo "[]" > ~/.claude/learnings-queue.json
```

## Validating plugin structure

Before committing structural changes (manifest, hooks, commands, skills), validate:

- `.claude-plugin/plugin.json` — valid JSON, `name` in kebab-case
- `hooks/hooks.json` — valid JSON, referenced scripts exist, uses `${CLAUDE_PLUGIN_ROOT}`
- `commands/*.md` — YAML frontmatter with `description`
- `skills/<name>/SKILL.md` — YAML frontmatter with `name` + `description`

The `plugin-dev` plugin's validator (`plugin-dev:plugin-validator` agent) checks
all of the above.
