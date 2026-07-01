# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

claude-reflect is a Claude Code plugin that implements a two-stage self-learning system:
1. **Capture Stage** (automatic): Hooks detect correction patterns in user prompts and queue them
2. **Process Stage** (manual): `/reflect` command processes queued learnings with human review and writes to CLAUDE.md files

## Architecture

```
.claude-plugin/plugin.json      → Plugin manifest
.claude-plugin/marketplace.json → Self-hosted single-plugin marketplace (source: "./")
hooks/hooks.json                → Hook definitions (PreCompact, PostToolUse)
scripts/                        → Python scripts for hooks and extraction
scripts/dev.sh                  → Launch a live-plugin dev session (--plugin-dir)
scripts/lib/                    → Shared utilities (paths/patterns/queue/memory/sessions; reflect_utils.py is a re-export shim)
scripts/legacy/                 → Deprecated bash scripts (for reference)
commands/*.md                   → Slash commands: /reflect, /reflect-skills, /skip-reflect, /view-queue
skills/claude-reflect/SKILL.md  → Auto-loaded skill (context surfaced when relevant)
tests/                          → Test suite (pytest)
```

### Data Flow

1. User prompt → `capture_learning.py` (UserPromptSubmit hook) → `~/.claude/learnings-queue.json`
2. `/reflect` command → reads queue + scans sessions → filters/dedupes → routes to memory targets
3. Session files live at `~/.claude/projects/[PROJECT_FOLDER]/*.jsonl`

### Memory Targets (Full Hierarchy)

| Target | Path | Type | Description |
|--------|------|------|-------------|
| Global CLAUDE.md | `~/.claude/CLAUDE.md` | `global` | Always enabled |
| Project CLAUDE.md | `./CLAUDE.md` | `root` | Project-specific |
| CLAUDE.local.md | `./CLAUDE.local.md` | `local` | Personal, gitignored |
| Subdirectory | `./**/CLAUDE.md` | `subdirectory` | Auto-discovered |
| Project Rules | `./.claude/rules/*.md` | `rule` | Modular, path-scoped |
| User Rules | `~/.claude/rules/*.md` | `user-rule` | Global modular rules |
| Auto Memory | `~/.claude/projects/<project>/memory/*.md` | `auto-memory` | Low-confidence staging |
| Skill Files | `./commands/*.md` | skill | Correction during skill use |
| AGENTS.md | `./AGENTS.md` | agents | Cross-tool standard |

### Key Files

- `scripts/lib/reflect_utils.py`: Re-export shim preserving the historical `from lib.reflect_utils import …` surface (split into the focused modules below)
- `scripts/lib/paths.py`: Path/config/sentinel utilities and timestamps
- `scripts/lib/patterns.py`: Regex detection — `detect_patterns`, `is_correction_candidate`, `Detection`
- `scripts/lib/queue.py`: Durable per-project queue I/O (atomic writes, `_QueueLock`, migration)
- `scripts/lib/memory.py`: Memory-hierarchy discovery, auto memory, rule frontmatter parsing, routing suggestions
- `scripts/lib/sessions.py`: Session-JSONL extraction and tool-error aggregation
- `scripts/lib/semantic_detector.py`: AI-powered semantic analysis via `claude -p` (used by `--scan-history`/`--organize`)
- `scripts/capture_learning.py`: Pattern detection (correction, positive, explicit markers) with confidence scoring
- `scripts/check_learnings.py`: PreCompact hook that backs up queue before context compaction
- `scripts/extract_session_learnings.py`: Extracts user messages from session JSONL files
- `scripts/extract_tool_rejections.py`: Extracts user corrections from tool rejections
- `scripts/compare_detection.py`: Compare regex vs semantic detection on session data
- `commands/reflect.md`: Main skill defining the /reflect workflow (memory hierarchy aware)
- `commands/reflect-skills.md`: Skill discovery - AI-powered pattern detection from sessions

## Development Commands

```bash
# Test capture hook with simulated input
echo '{"prompt":"no, use gpt-5.1 not gpt-5"}' | python3 scripts/capture_learning.py

# View current learnings queue
cat ~/.claude/learnings-queue.json

# Test session extraction
python3 scripts/extract_session_learnings.py ~/.claude/projects/[PROJECT]/*.jsonl --corrections-only

# Run tests
python -m pytest tests/ -v

# Clear queue for testing
echo "[]" > ~/.claude/learnings-queue.json
```

### Local development (live editing)

Load the plugin directly from this repo so edits take effect (no reinstall):

```bash
./scripts/dev.sh          # == claude --plugin-dir "$(pwd)"
# then, after any edit, inside the session:
/reload-plugins
```

`/plugin install` instead copies the plugin to `~/.claude/plugins/cache/` (a
frozen snapshot — repo edits won't apply). See [DEVELOPMENT.md](DEVELOPMENT.md)
for the full install-vs-dev breakdown.

## Plugin Structure

The plugin registers via `.claude-plugin/plugin.json`. All components are
auto-discovered by convention (no explicit paths in the manifest):
- Hooks are defined in `hooks/hooks.json`
- Commands are markdown files in `commands/` (surfaced as `/reflect` etc.)
- The skill lives at `skills/claude-reflect/SKILL.md` — auto-loaded and surfaced
  to Claude when relevant. (A `SKILL.md` at the repo root is NOT discovered; it
  must be under `skills/<name>/`.)

### Hook Events

| Hook | Script | Purpose |
|------|--------|---------|
| SessionStart | `session_start_reminder.py` | Show pending learnings reminder |
| UserPromptSubmit | `capture_learning.py` | Detect corrections and queue them |
| PreCompact | `check_learnings.py` | Backup queue before compaction |
| PostToolUse (Bash) | `post_commit_reminder.py` | Remind to /reflect after commits |

## Detection Methods

### Regex Patterns (Real-time)

`scripts/lib/patterns.py` defines pattern detection (recall-biased at capture per
ADR-0001 — precision is judged inline during `/reflect`):
- **Corrections**: "no, use X", "don't use", "stop using", "that's wrong", "actually", "use X not Y"
- **Positive**: "perfect!", "exactly right", "great approach", "nailed it"
- **Explicit**: "remember:" prefix (highest confidence)

Confidence scores range 0.55-0.90 based on pattern strength and count.

### Precision (During /reflect)

Per [ADR-0001](docs/adr/0001-detection-recall-at-capture-precision-at-process.md),
the **learning path judges precision inline**: the `/reflect` agent reads each
queued item to present it and decides reusability in-context — no subprocess, no
`claude -p`. This retired the semantic silent-bypass bug by construction (there is
no subprocess left to be unavailable) and deleted `validate_queue_items`.

`scripts/lib/semantic_detector.py` remains for the two out-of-scope flows only:
- `validate_tool_errors(...)` — `--scan-history` tool-error classification
- `detect_contradictions(...)` — `--organize` contradiction detection
- `semantic_analyze(text)` — shared primitive (also used by `compare_detection.py`)

### Comparison Testing

`scripts/compare_detection.py` compares regex vs semantic detection:
```bash
python scripts/compare_detection.py --project .
```

## Session File Format

Session files are JSONL at `~/.claude/projects/[PROJECT_FOLDER]/`:
- User messages: `{"type": "user", "message": {"content": [{"type": "text", "text": "..."}]}, "isMeta": false}`
- Tool rejections: `{"type": "user", "message": {"content": [{"type": "tool_result", "is_error": true, "content": "...the user said:\n[feedback]"}]}}`
- Filter `isMeta: true` to exclude command expansions

## Queue Item Structure

```json
{
  "type": "auto|explicit|positive|guardrail",
  "message": "user's original text",
  "timestamp": "ISO8601",
  "project": "/path/to/project",
  "patterns": "matched pattern names",
  "confidence": 0.75,
  "sentiment": "correction|positive",
  "decay_days": 90
}
```

## Skill Discovery (/reflect-skills)

Analyzes session history to discover repeating patterns that could become skills.

**Design Principles:**
- **AI-powered** — Claude uses reasoning to identify patterns, not regex
- **Semantic similarity** — detects same intent across different phrasings
- **Human-in-the-loop** — user approves before skill generation

**Usage:**
```bash
/reflect-skills              # Analyze last 14 days
/reflect-skills --days 30    # Analyze last 30 days
/reflect-skills --dry-run    # Preview without generating files
```

**What it detects:**
- Workflow patterns (repeated multi-step sequences)
- Misunderstanding patterns (corrections that could become guardrails)
- Intent similarity (same goal, different wording)

## Skill Improvement Routing

When running `/reflect`, corrections made during skill execution can be routed back to the skill file itself.

**How it works:**
1. `/reflect` detects when a correction followed a skill invocation (e.g., `/deploy`)
2. Claude reasons about whether the correction relates to the skill's workflow
3. User is offered routing options: skill file | CLAUDE.md | both
4. Skill file is updated in the appropriate section (steps, guardrails, etc.)

**Example:**
```
User: /deploy
Claude: [deploys without running tests]
User: "no, always run tests before deploying"

→ /reflect detects this relates to /deploy
→ Offers to add "Run tests before deploying" to commands/deploy.md
→ Skill file updated with new step in workflow
```

## Platform Support

- **macOS**: Fully supported
- **Linux**: Fully supported
- **Windows**: Fully supported (native Python, no WSL required)

Requires Python 3.8+ (matches the CI floor).

## Releasing

See [RELEASING.md](RELEASING.md) for version bump checklist and release process.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues on this fork (`caioniehues/claude-reflect`) via the `gh` CLI; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), created on first use. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
