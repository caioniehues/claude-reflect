---
description: Reflect on session corrections and update CLAUDE.md (with human review)
allowed-tools: Read, Edit, Write, Glob, Bash, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList, TaskGet
---

## Arguments
- `--dry-run`: Preview all changes without prompting or writing.
- `--scan-history`: Scan ALL past sessions for corrections (useful for first-time setup or cold start).
- `--all-projects`: **Global harvest.** Sweep session history across EVERY project, dedupe corrections cross-project, and surface the ones worth promoting to global `~/.claude/CLAUDE.md` (ranked by how many projects each recurred in). Implies `--scan-history`, forces `global` scope, only ever writes global. Composes with `--days` and `--dry-run`.
- `--days N`: Limit history scan to last N days (default: 30 for `--scan-history`; **90 for `--all-projects`**). Only used with history scans.
- `--targets`: Show detected AI assistant config files and exit.
- `--review`: Show learnings with stale/decayed entries for review.
- `--dedupe`: Scan CLAUDE.md for similar entries and propose consolidations.
- `--organize`: Analyze memory hierarchy and suggest reorganization across tiers.
- `--include-tool-errors`: Include project-specific tool execution errors in scan (auto-enabled with `--scan-history`).
- `--model MODEL`: Model for semantic analysis (default: `sonnet`). Use `haiku` for faster/cheaper runs or `opus` for maximum accuracy.

## Context
- Project CLAUDE.md: @CLAUDE.md
- Global CLAUDE.md: @~/.claude/CLAUDE.md
- Learnings queue (per-project): !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/read_queue.py" 2>/dev/null || echo "[]"`
- Current project: !`pwd`

## Multi-Target Export

Claude-reflect syncs learnings to CLAUDE.md files (including subdirectories), skill files, and AGENTS.md.

**Supported Targets:**

| Target | File Path | Format | Notes |
|--------|-----------|--------|-------|
| **Global CLAUDE.md** | `~/.claude/CLAUDE.md` | Markdown | Always enabled |
| **Project CLAUDE.md** | `./CLAUDE.md` | Markdown | If exists |
| **CLAUDE.local.md** | `./CLAUDE.local.md` | Markdown | Personal, gitignored |
| **Subdirectory CLAUDE.md** | `./**/CLAUDE.md` | Markdown | Auto-discovered |
| **Project Rules** | `./.claude/rules/*.md` | Markdown | Modular rules, optional path-scoping |
| **User Rules** | `~/.claude/rules/*.md` | Markdown | Global modular rules |
| **Skill Files** | `./.claude/commands/*.md` (project), `~/.claude/commands/*.md` (user) | Markdown | When correction relates to skill |
| **Auto Memory** | `~/.claude/projects/<project>/memory/*.md` | Markdown | Low-confidence, exploratory learnings |
| **AGENTS.md** | `./AGENTS.md` | Markdown | Industry standard (Codex, Cursor, Aider, Jules, Zed, Factory) |

**Target Discovery:**

Use the Python utility to find all memory tier files:
```python
from scripts.lib.reflect_utils import find_claude_files
files = find_claude_files()
# Returns list of {path, relative_path, type, frontmatter}
# Types: 'global', 'root', 'local', 'subdirectory', 'rule', 'user-rule'
```

Or discover manually:
```bash
# Find all CLAUDE.md files (excluding node_modules, .git, venv, etc.)
find . -name "CLAUDE.md" -type f \
  -not -path "*/node_modules/*" \
  -not -path "*/.git/*" \
  -not -path "*/venv/*" \
  -not -path "*/.venv/*"
# Also check rule files and local
ls .claude/rules/*.md 2>/dev/null
ls CLAUDE.local.md 2>/dev/null
ls ~/.claude/rules/*.md 2>/dev/null
```

**Target Selection (Hierarchy-Aware Routing):**
- **Guardrail corrections** ("don't do X") → `.claude/rules/guardrails.md`
- **Model preferences** → existing model-preferences rule file or `~/.claude/CLAUDE.md`
- **Global behavioral** (always/never/prefer) → `~/.claude/CLAUDE.md`
- **Path-scoped** (learning mentions directory covered by rule's `paths:`) → that rule file
- **Personal/local** (machine-specific, not for team) → `./CLAUDE.local.md`
- **Low-confidence** (0.60-0.74) → auto memory for later promotion
- **Project-specific** → `./CLAUDE.md` or subdirectory file
- Let users override routing with AI reasoning

**Note on Confidence & Decay:**
- Confidence scores help prioritize learnings during `/reflect` review
- Decay applies to **queue items only** — if a learning sits unprocessed for too long, it's flagged as stale
- Once applied to CLAUDE.md, entries are permanent (edit manually to remove)

## Your Task

### Operating principle: surface, don't suppress

One rule governs every filtering decision in this workflow: **surface, don't
suppress.** Capture is a wide recall net (ADR-0001); precision is your job here,
in front of the user, never a silent drop. Concretely:

- If extraction found *any* matches, present them — never conclude "0 learnings"
  while raw matches or tool rejections exist unshown.
- When in doubt, include it and let the user decide. A borderline item shown
  costs one glance; a borderline item suppressed is lost.
- `remember:` items and queue items are **never** filtered out — the user already
  chose to capture them.
- Tool rejections are high-signal corrections — always show them, even ones that
  look task-specific.

Later steps reference this principle rather than restating it.

### Initialize Task Tracking

Before starting, use **TaskCreate** to register the workflow phases so none is
skipped, and **TaskUpdate** each to `in_progress`/`completed` as you go (adjust
to the arguments passed):

1. Parse arguments and check flags
2. Load learnings queue
3. Scan historical sessions (if `--scan-history`)
4. Judge reusability inline (Step 1.5)
5. Filter by project context
6. Deduplicate similar learnings
7. Check existing memory tiers for duplicates
8. Present summary and get user decision
9. Apply changes
10. Clear queue and confirm

---

### Handle Flag Arguments (early-exit branches)

Some flags short-circuit the normal workflow. If the user passed one, read the
matching reference file, follow it, then exit **without processing the queue**:

| Flag | Reference file (read on demand) |
|------|----------------------------------|
| `--targets` | `${CLAUDE_PLUGIN_ROOT}/commands/reflect/targets.md` |
| `--review` | `${CLAUDE_PLUGIN_ROOT}/commands/reflect/review.md` |
| `--dedupe` | `${CLAUDE_PLUGIN_ROOT}/commands/reflect/dedupe.md` |
| `--organize` | `${CLAUDE_PLUGIN_ROOT}/commands/reflect/organize.md` |

`--scan-history` does NOT exit early — it feeds the normal workflow (see Step 0.5).

`--all-projects` also does NOT exit early — it is a self-sufficient flag that
**implies `--scan-history`** and **forces `global` scope**. When present, read
`${CLAUDE_PLUGIN_ROOT}/commands/reflect/all-projects.md` and follow it *instead of*
the per-project Step 0.5 scan. `--scan-history --all-projects` is accepted and
identical to `--all-projects` alone.

### First-Run Detection (Per-Project)

Check if /reflect has been run in THIS project before. Run these commands separately:

**WARNING**: Do NOT combine these into a single compound command with `$(...)`. Claude Code's bash executor mangles subshell syntax. Run each command individually and manually substitute the result.

1. Find the project folder name:
```bash
ls ~/.claude/projects/ | grep -i "$(basename "$(pwd)")"
```

2. Check if initialized (replace PROJECT_FOLDER with result from step 1):
```bash
test -f ~/.claude/projects/PROJECT_FOLDER/.reflect-initialized && echo "initialized" || echo "first-run"
```

**If user passed `--all-projects`, SKIP first-run detection entirely** — go
straight to the global harvest (Step 0, `--all-projects` branch). The global sweep
is inherently a cold-start recovery path and must not be intercepted by a
per-project first-run offer.

**If "first-run" for this project AND user did NOT pass `--scan-history` or `--all-projects`:**

Use AskUserQuestion to recommend historical scan:
```json
{
  "questions": [{
    "question": "First time running /reflect in this project. Scan past sessions for learnings?",
    "header": "First run",
    "multiSelect": false,
    "options": [
      {"label": "Yes, scan history (Recommended)", "description": "Find corrections from past sessions in this project"},
      {"label": "No, just process queue", "description": "Only process learnings captured by hooks"}
    ]
  }]
}
```

If user chooses "Yes, scan history", proceed as if `--scan-history` was passed.

### Step 0: Check Arguments

**If user passed `--dry-run`:**
- Process all learnings with project filtering
- Show proposed changes with line numbers
- Do NOT prompt for actions, do NOT write
- End with: "Dry run complete. Run /reflect without --dry-run to apply."

**If user passed `--scan-history`:**
- FIRST: Load the queue (Step 1) - queued items are NEVER skipped
- THEN: Scan ALL historical sessions for this project (Step 0.5)
- Combine queue items + history scan results into working list
- Proceed to Step 3 (Project-Aware Filtering)

**If user passed `--all-projects`:**
- This is a **global harvest** — do NOT process the per-project queue or run the
  per-project Step 0.5 scan.
- Read `${CLAUDE_PLUGIN_ROOT}/commands/reflect/all-projects.md` and follow it end
  to end. It runs the cross-project sweep (pass-1 script), judges the shortlist
  inline, writes only to global `~/.claude/CLAUDE.md`, and lists project-specific
  finds per project. `--days` and `--dry-run` compose as documented there.
- Then exit (do not fall through to the normal queue workflow).

### Step 0.5: Historical Scan (only with --scan-history)

Only when `--scan-history` was passed (or the first-run offer was accepted): read
`${CLAUDE_PLUGIN_ROOT}/commands/reflect/scan-history.md` and follow it to scan
past sessions for missed corrections and tool-error patterns. It ADDS results to
the working list; continue to Step 3 with the combined list.

### Step 1: Load and Validate
- Read the queue from `~/.claude/learnings-queue.json`
- Add all queue items to the working list (mark source as "queued")
- **IMPORTANT**: Even if queue is empty, continue if `--scan-history` will add items
- Only exit early if: queue is empty AND not doing history scan AND user declines manual capture

### Step 1.5: Judge Reusability Inline (Queue Items)

Capture is a wide **recall** net (ADR-0001): the queue over-captures on purpose,
so a real correction is never permanently dropped in an always-on hook where a
miss is unreviewable. Precision lives **here**, judged inline by you as you read
each item to present it — no subprocess, no `claude -p`, no separate pass. You
are already the smartest model in the loop; a second Claude judging what you're
about to show the user is redundant.

**1.5a. For each queued item, judge whether it is a reusable learning.**

Read `item["message"]` and decide, in one pass, in any language:
- **Keep** if it expresses a durable preference, correction, or guardrail that
  should shape future behavior (e.g. "use pnpm not npm", "don't add docstrings
  unless asked", "remember: deploy from staging first").
- **Drop** if it is transient chatter with no reusable signal — a greeting, a
  one-off question, agreement ("no problem"), or a task instruction that only
  applied to that moment ("perfect! now add the column"). Dropping here is safe:
  it is a reviewed, in-session call, not a silent capture-time deletion.

For kept items, write a concise, actionable `extracted_learning` (the clean
statement that would go into a memory file) and note its type
(correction / positive / explicit / guardrail).

**1.5b. `remember:` items are ALWAYS kept** — explicit user requests are never
dropped, regardless of your reusability judgment.

**1.5c. Report what you dropped**, so the user can catch a bad call:
```
═══════════════════════════════════════════════════════════
INLINE REVIEW — [N] queued items
═══════════════════════════════════════════════════════════
  ✓ [M] kept as learnings
  ✗ [K] dropped (no reusable signal)

Dropped:
  - "Hello, how are you?" — greeting
  - "perfect! now add the column" — one-off task instruction
═══════════════════════════════════════════════════════════
```

### Step 1.6: Auto Memory Enrichment

Scan auto memory for entries that may deserve "promotion" to CLAUDE.md, and route low-confidence items downward.

**1.6a. Check auto memory for promotion candidates:**

```python
from scripts.lib.reflect_utils import read_auto_memory
auto_entries = read_auto_memory()
# Look for entries that have been validated by repeated use
```

If auto memory entries exist, scan for patterns that appear in multiple topic files or have been manually confirmed — these are candidates for promotion to CLAUDE.md.

**1.6b. Route low-confidence queue items to auto memory:**

For items with confidence 0.60-0.74 that you judged reusable inline (Step 1.5):
- Offer auto memory as a destination instead of CLAUDE.md
- Auto memory is a "staging area" — items can be promoted later via `/reflect --organize`

```
Learning: "Try using batch mode for large datasets" (confidence: 0.65)
→ Suggested destination: Auto Memory (model-preferences.md)
  Reason: Low confidence — store in auto memory for now, promote later if confirmed
```

Use AskUserQuestion when routing to auto memory:
```json
{
  "questions": [{
    "question": "Low-confidence learning — where should it go?",
    "header": "Route",
    "multiSelect": false,
    "options": [
      {"label": "Auto Memory (Recommended)", "description": "Store in auto memory for later promotion"},
      {"label": "CLAUDE.md", "description": "Add to CLAUDE.md despite low confidence"},
      {"label": "Skip", "description": "Don't store this learning"}
    ]
  }]
}
```

### Step 2: Session Reflection (Enhanced with History Analysis)

**Note**: This step is for analyzing the CURRENT session only (when NOT using `--scan-history`).
If `--scan-history` was passed, skip to Step 3 with results from Step 0.5.

Analyze the current session for corrections missed by real-time hooks:

**2a. Find current session file:**

List session files for this project (most recent first):
```bash
ls -lt ~/.claude/projects/ | grep -i "$(basename $(pwd))"
```

Then list files in that folder and pick the most recent non-agent file:
```bash
ls -lt ~/.claude/projects/[PROJECT_FOLDER]/*.jsonl | head -5
```

Agent files (`agent-*.jsonl`) are sub-conversations; focus on main session files for current session analysis.

**2b. Extract tool rejections (HIGH confidence corrections):**

Search the current session file for `toolUseResult` fields containing "user said:" followed by feedback. These are high-confidence corrections.

- "user said:" followed by empty content = rejection without feedback, skip these
- Extract the feedback text after "user said:" for processing

**2c. Extract user messages with correction patterns:**

Search the current session file for user messages matching correction patterns. Use the same patterns from Step 0.5b. Remember:
- Filter out `isMeta: true` entries (command expansions like /reflect itself)
- Apply language-specific patterns if conversation is non-English

**2d. Also reflect on conversation context:**
- Were there any corrections or patterns not explicitly queued?
- Model names, API patterns, tool usage mistakes, project conventions?
- Implicit corrections (e.g., "Actually, the API returns...")

**2e. Judge reusability inline:**

Judge corrections from 2b/2c the same way as Step 1.5 and Step 0.5d — inline, no
subprocess — under **surface, don't suppress**:
- REJECT only questions, one-time tasks, context-specific items, vague feedback
- ACCEPT tool recommendations, patterns, conventions, model corrections
- Write each accepted item as an actionable learning in imperative form, with a
  scope suggestion

**2f. Add findings to working list:**
For each ACCEPTED learning:
- Use the actionable learning you created as the proposed entry
- Use the scope suggestion (global/project) as default
- Add to working list alongside queued items
- Mark source type:
  - "queued" — from hooks/explicit remember:
  - "session-scan" — from message pattern matching
  - "tool-rejection" — from tool rejections (HIGH confidence)

### Step 3: Project-Aware Filtering

Get current project path. For each queue item, compare `item.project` with current project:

**CASE A: Same project**
- Show normally
- Offer: [a]pprove | [e]dit | [s]kip
- If approve, ask scope: [p]roject | [g]lobal | [b]oth

**CASE B: Different project, looks GLOBAL**
(message contains: gpt-*, claude-*, model names, general patterns like "always/never")
- Show with warning: "⚠️ FROM DIFFERENT PROJECT"
- Show: "Captured in: [original-project]"
- Offer: [g]lobal | [s]kip (NOT project - wrong context)

**CASE C: Different project, looks PROJECT-SPECIFIC**
(message contains: specific DB names, file paths, project-specific tools)
- Auto-skip with note: "Skipping project-specific learning from [other-project]"
- Offer: [f]orce to add to global anyway

**Heuristics:**
- `gpt-[0-9]` or `claude-` → GLOBAL (model name)
- `always|never|don't` + generic verb → GLOBAL (general rule)
- Specific tool/DB/service names → PROJECT-SPECIFIC
- File paths → PROJECT-SPECIFIC

### Step 3.3: Skill Context Detection (AI-Powered)

For each learning, reason about whether it relates to an **active skill**.

**IMPORTANT: Use reasoning, not pattern matching.**

Read the session context around the correction. Think:
- Was a skill/command (e.g., `/deploy`, `/commit`) invoked before this correction?
- Does the correction relate to HOW that skill should work?
- Would this correction be better as an improvement to the skill file itself?

**Example reasoning:**
```
Learning: "always run tests before deploying"
Session context: User ran /deploy, then corrected me

My analysis: This correction happened right after /deploy was invoked.
The user wants the deploy skill to include running tests.
This should be offered as a skill improvement, not a CLAUDE.md entry.
```

**For each skill-related learning, add metadata:**
```json
{
  "skill_context": {
    "skill_name": "deploy",
    "skill_file": ".claude/commands/deploy.md",
    "reason": "Correction followed /deploy invocation"
  }
}
```

**Detection approach:**
1. Look for `/command` patterns in recent session messages
2. Reason about whether the correction relates to that command's workflow
3. Check if the command file exists. Commands live at `.claude/commands/[skill-name].md`
   (project) or `~/.claude/commands/[skill-name].md` (user) — this is the single
   source of truth shared with `/reflect-skills`. Prefer the project file if both exist.

**If skill context detected:**
- Mark the learning with skill metadata
- In Step 5, offer routing options: skill file | CLAUDE.md | both

**If NO skill context detected:**
- Continue with normal CLAUDE.md routing

### Step 3.5: Semantic Deduplication (Within Queue)

Before checking against CLAUDE.md, consolidate similar learnings within the current batch.

**3.5a. Group by semantic similarity:**

Analyze all learnings in the working list. Look for entries that:
- Reference the same tool, model, or concept
- Give similar advice (even with different wording)
- Could be consolidated into a single, clearer entry

**Example - Before consolidation:**
```
1. "Use gpt-5.1 for complex tasks"
2. "Prefer gpt-5.1 over gpt-5 for reasoning"
3. "gpt-5.1 is better for hard problems"
```

**Example - After consolidation:**
```
1. "Use gpt-5.1 for complex reasoning (replaces gpt-5)"
```

**3.5b. Present consolidation proposals:**

If similar learnings are detected, show:
```
═══════════════════════════════════════════════════════════
SIMILAR LEARNINGS DETECTED
═══════════════════════════════════════════════════════════

These 3 learnings appear related:
  #2: "Use gpt-5.1 for complex tasks"
  #5: "Prefer gpt-5.1 over gpt-5 for reasoning"
  #7: "gpt-5.1 is better for hard problems"

Proposed consolidation:
  → "Use gpt-5.1 for complex reasoning tasks (replaces gpt-5)"

═══════════════════════════════════════════════════════════
```

**3.5c. Use AskUserQuestion for consolidation:**

```json
{
  "questions": [{
    "question": "Consolidate these 3 similar learnings into one?",
    "header": "Dedupe",
    "multiSelect": false,
    "options": [
      {"label": "Yes, consolidate", "description": "Merge into: 'Use gpt-5.1 for complex reasoning tasks'"},
      {"label": "Keep separate", "description": "Add all 3 as individual entries"},
      {"label": "Edit consolidation", "description": "Let me modify the merged text"}
    ]
  }]
}
```

**3.5d. Consolidation rules:**
- Keep highest confidence score from the group
- Combine decay_days (use longest)
- Mark source as "consolidated"
- If user chooses "Edit", allow them to provide custom text

**3.5e. Skip if no duplicates:**
- If all learnings are semantically distinct, proceed to Step 4
- Only show consolidation UI when similar entries are detected

### Step 4: Duplicate Detection with Line Numbers (All Memory Tiers)

For each learning kept after filtering, search ALL memory tiers:

```bash
# CLAUDE.md files
grep -n -i "keyword" ~/.claude/CLAUDE.md
grep -n -i "keyword" CLAUDE.md
grep -n -i "keyword" CLAUDE.local.md 2>/dev/null

# Rule files
grep -rn -i "keyword" .claude/rules/ 2>/dev/null
grep -rn -i "keyword" ~/.claude/rules/ 2>/dev/null

# Auto memory
grep -rn -i "keyword" ~/.claude/projects/PROJECT_FOLDER/memory/ 2>/dev/null
```

Or use the cross-tier deduplication utility:
```python
from scripts.lib.reflect_utils import read_all_memory_entries
entries = read_all_memory_entries()
# Returns [{text, source_file, source_type, line_number}, ...]
# Search entries for semantic similarity to each learning
```

If duplicate found:
- Show: "⚠️ SIMILAR in [source_type] [source_file]: Line [N]: [content]"
- Offer: [m]erge | [r]eplace | [a]dd anyway | [s]kip

### Step 5: Present Summary and Get User Decision

**5a. Display condensed summary table:**

Show all learnings in a compact table format:

```
════════════════════════════════════════════════════════════
LEARNINGS SUMMARY — [N] items found
════════════════════════════════════════════════════════════

┌────┬─────────────────────────────────────────┬──────────┬────────┐
│ #  │ Learning                                │ Target   │ Status │
├────┼─────────────────────────────────────────┼──────────┼────────┤
│ 1  │ Use DB for persistent storage           │ project  │ ✓ new  │
│ 2  │ Backoff on actual errors only           │ global   │ ✓ new  │
│ 3  │ Run tests before deploying              │ /deploy  │ ⚡skill │
│ ...│ ...                                     │ ...      │ ...    │
└────┴─────────────────────────────────────────┴──────────┴────────┘

Destinations: [N] → Global, [M] → Project, [K] → Skills
Duplicates: [L] items will be merged with existing entries
```

**5a.1. Skill-Related Learnings (if any detected):**

If any learnings have `skill_context` metadata from Step 3.3, show them separately:

```
════════════════════════════════════════════════════════════
SKILL IMPROVEMENTS DETECTED
════════════════════════════════════════════════════════════

These learnings appear related to specific skills:

#3: "Run tests before deploying"
   → Relates to: /deploy (.claude/commands/deploy.md)
   → Reason: Correction followed /deploy invocation

#7: "Include file count in commit message"
   → Relates to: /commit (.claude/commands/commit.md)
   → Reason: Correction during commit workflow

════════════════════════════════════════════════════════════
```

**5a.2. Skill Routing Question:**

For each skill-related learning, use AskUserQuestion:
```json
{
  "questions": [{
    "question": "Learning #3 relates to /deploy. Where should it go?",
    "header": "Route",
    "multiSelect": false,
    "options": [
      {"label": "Skill file (Recommended)", "description": "Add to .claude/commands/deploy.md to improve the skill"},
      {"label": "CLAUDE.md", "description": "Add to project CLAUDE.md as general guidance"},
      {"label": "Both", "description": "Add to skill file AND CLAUDE.md"},
      {"label": "Skip", "description": "Don't add this learning anywhere"}
    ]
  }]
}
```

Track routing decisions for Step 7.

**5b. Use AskUserQuestion for strategy:**

Use the AskUserQuestion tool:
```json
{
  "questions": [{
    "question": "How would you like to process these [N] learnings?",
    "header": "Action",
    "multiSelect": false,
    "options": [
      {"label": "Apply all (Recommended)", "description": "Add [X] new entries, merge [K] duplicates with recommended scopes"},
      {"label": "Select which to apply", "description": "Choose specific learnings from grouped lists"},
      {"label": "Review details first", "description": "Show full details for each learning before deciding"},
      {"label": "Skip all", "description": "Don't apply any learnings, clear the queue"}
    ]
  }]
}
```

**5c. Handle user selection:**

- **"Apply all"** → Proceed to Step 6 (Final Confirmation)
- **"Select which to apply"** → Go to Step 5.1 (Selection Mode)
- **"Review details first"** → Show full learning cards (format below), then return to 5b
- **"Skip all"** → Go to Step 8 (Clear Queue)

**Full learning card format (for "Review details first"):**
```
════════════════════════════════════════════════════════════
LEARNING [N] of [TOTAL] — [source: queued/session-scan/tool-rejection]
════════════════════════════════════════════════════════════
Original message:
  "[the user's original text]"

Proposed addition:
┌──────────────────────────────────────────────────────────┐
│ ## [Section Name]                                        │
│ - [Exact bullet point that will be added]                │
└──────────────────────────────────────────────────────────┘

Duplicate check:
  ✓ None found
  OR
  ⚠️ SIMILAR in [global/project] CLAUDE.md:
     Line [N]: "[existing content]"
════════════════════════════════════════════════════════════
```

### Step 5.1: Selection Mode (if user chose "Select which to apply")

Group learnings by destination and use AskUserQuestion with multiSelect.

**Rules:**
- Split into multiple questions if >4 items per destination
- Use short labels: "#{N} {short_title}" (max 20 chars)
- Use descriptions for full learning text (max 80 chars)

**Example for GLOBAL learnings:**
```json
{
  "questions": [
    {
      "question": "Select GLOBAL learnings to apply:",
      "header": "Global",
      "multiSelect": true,
      "options": [
        {"label": "#2 Backoff errors", "description": "Implement backoff only on actual errors, not artificial delays"},
        {"label": "#3 DB cache", "description": "Use local database cache to minimize data fetching"},
        {"label": "#4 Batch+delays", "description": "Use batching with stochastic delays for API rate limits"},
        {"label": "#5 Use venv", "description": "Always use virtual environments for Python projects"}
      ]
    }
  ]
}
```

**If >4 global items:** Add second question with header "Global+"

**Example for PROJECT learnings:**
```json
{
  "questions": [
    {
      "question": "Select PROJECT learnings to apply:",
      "header": "Project",
      "multiSelect": true,
      "options": [
        {"label": "#1 DB storage", "description": "Use database for persistent tracking data"},
        {"label": "#6 DB ports", "description": "Assign unique ports per database instance"}
      ]
    }
  ]
}
```

**Selection rules:**
- Items NOT selected will be skipped
- Continue to Step 6 with selected items only

### Step 6: Final Confirmation

**6a. Show summary of changes:**
```
════════════════════════════════════════════════════════════
SUMMARY: [N] changes ready to apply
════════════════════════════════════════════════════════════

Project CLAUDE.md ([path]):
  Line [N]: UPDATE "[old]" → "[new]"
  After line [N]: ADD "[new entry]"

Global CLAUDE.md (~/.claude/CLAUDE.md):
  Line [N]: REPLACE "[old]" → "[new]"
  After line [N]: ADD "[new entry]"

Skill Files:
  .claude/commands/deploy.md: ADD "Run tests before build step"
  .claude/commands/commit.md: ADD "Include file count in message"

Skipped: [N] learnings (including [M] from other projects)
════════════════════════════════════════════════════════════
```

**6b. Use AskUserQuestion for confirmation:**
```json
{
  "questions": [{
    "question": "Apply [N] learnings to target files?",
    "header": "Confirm",
    "multiSelect": false,
    "options": [
      {"label": "Yes, apply all", "description": "[X] to Global, [Y] to Project, [Z] to Skills"},
      {"label": "Go back", "description": "Return to selection to adjust"},
      {"label": "Cancel", "description": "Don't apply anything, keep queue"}
    ]
  }]
}
```

**6c. Handle response:**
- **"Yes, apply all"** → Proceed to Step 7
- **"Go back"** → Return to Step 5b
- **"Cancel"** → Exit without changes (keep queue intact)

### Step 7: Apply Changes

Only after final confirmation:

**7a. Apply to CLAUDE.md (Primary Targets):**
1. Read current CLAUDE.md files
2. Use Edit tool with precise old_string from detected line numbers
3. For new entries, add after the relevant section header

**7a.1. Apply to Rule Files (if any routed to rules):**

For learnings routed to `.claude/rules/*.md`:

1. Check if the target rule file exists; if not, create it:
   - Ask user to confirm filename for new rule files
   - Naming conventions: `guardrails.md`, `model-preferences.md`, `coding-style.md`, `testing.md`, etc.
2. If the rule is path-specific, add YAML frontmatter:
   ```markdown
   ---
   paths:
     - "src/"
     - "lib/"
   ---
   ```
3. Append the learning as a bullet point under an appropriate heading
4. For `~/.claude/rules/*.md` (user-level rules), use the same approach

**7a.2. Apply to Auto Memory (if low-confidence or exploratory):**

For learnings routed to auto memory (typically confidence 0.60-0.74):

1. Use `suggest_auto_memory_topic()` to determine filename:
   ```python
   from scripts.lib.reflect_utils import suggest_auto_memory_topic, get_auto_memory_path
   topic = suggest_auto_memory_topic(learning_text)  # e.g., "model-preferences"
   memory_dir = get_auto_memory_path()
   ```
2. Create memory directory if missing: `memory_dir.mkdir(parents=True, exist_ok=True)`
3. Write/append to topic file (`{topic}.md`) in markdown format:
   ```markdown
   # Model Preferences
   - Use gpt-5.1 for reasoning tasks (confidence: 0.65, 2026-02-12)
   ```
4. Auto memory entries can later be "promoted" to CLAUDE.md via `/reflect --organize`

**7b. Apply to Skill Files (if any routed to skills):**

For learnings routed to skill files in Step 5a.2:

1. Read the skill file (e.g., `.claude/commands/deploy.md`)
2. Reason about WHERE the learning fits in the skill:
   - Is it a new step in the workflow? → Add to steps section
   - Is it a guardrail/constraint? → Add to guardrails section
   - Is it context/setup? → Add to context section
3. Use Edit tool to insert the learning appropriately

**Example skill file update:**
```markdown
## Steps

1. Run tests                    ← NEW (added from learning)
2. Build the project
3. Push to production
4. Notify Slack

## Guardrails
- Always verify tests pass before proceeding  ← Could also go here
```

**Important:**
- Preserve the skill's existing structure
- Add learnings where they make semantic sense
- Use your reasoning to determine placement (not hardcoded rules)

**7c. Apply to AGENTS.md (if exists):**

Check if AGENTS.md exists:
```bash
test -f AGENTS.md && echo "AGENTS.md found"
```

If AGENTS.md exists, apply the SAME learnings using this format:

```markdown
## Claude-Reflect Learnings

<!-- Auto-generated by claude-reflect. Do not edit this section manually. -->

### Model Preferences
- Use gpt-5.1 for reasoning tasks

### Tool Usage
- Use local database cache to minimize API calls

<!-- End claude-reflect section -->
```

**Update Strategy:**
- Look for existing `<!-- Auto-generated by claude-reflect` marker
- If found: REPLACE the entire section (from marker to `<!-- End claude-reflect section -->`)
- If not found: APPEND section at the end of the file
- Always preserve user's existing content outside the marked section

### Step 8: Clear Queue

```bash
echo "[]" > ~/.claude/learnings-queue.json
```

### Step 9: Confirm

```
════════════════════════════════════════════════════════════
DONE: Applied [N] learnings
════════════════════════════════════════════════════════════
  ✓ ~/.claude/CLAUDE.md    [N] entries
  ✓ ./CLAUDE.md            [N] entries
  ✓ AGENTS.md              [N] entries (if exists)
  ⚡ .claude/commands/deploy.md     [N] skill improvements
  ⚡ .claude/commands/commit.md     [N] skill improvements

  Skipped: [N]
════════════════════════════════════════════════════════════
```

### Step 10: Mark Initialized (Per-Project)

Create marker file for THIS project so first-run detection won't trigger again.
Use the PROJECT_FOLDER you found in First-Run Detection:

```bash
touch ~/.claude/projects/PROJECT_FOLDER/.reflect-initialized
```

Replace PROJECT_FOLDER with the actual folder name (e.g., `-Users-bob-myproject`).

## Formatting Rules

- **Bullets, not prose**: Keep entries as single bullet points
- **Actionable**: "Use X for Y" not "X is better than Y"
- **Concise**: Max 2 lines per entry
- **Examples when helpful**: `(e.g., gpt-5.2 not gpt-5.1)`

## Section Headers

Use these standard headers:
- `## LLM Model Recommendations` — model names, versions
- `## Tool Usage` — MCP, APIs, which tool for what
- `## Project Conventions` — coding style, patterns
- `## Guardrails` — constraints and "don't do X" rules
- `## Common Errors to Avoid` — gotchas, mistakes
- `## Environment Setup` — venv, configs, paths

### Rule File Mapping

When routing learnings to `.claude/rules/` files, use this mapping:

| Learning Type | Suggested Rule File | Create If Missing |
|---------------|--------------------|--------------------|
| Guardrails / "don't do X" | `guardrails.md` | Yes |
| Model preferences | `model-preferences.md` | Yes |
| Coding style / formatting | `coding-style.md` | Yes |
| Testing conventions | `testing.md` | Yes |
| Path-specific rules | `{context}.md` with `paths:` frontmatter | Ask user |

**YAML Frontmatter for Path-Scoped Rules:**

When a learning applies only to specific directories, create the rule file with frontmatter:
```markdown
---
paths:
  - "src/api/"
  - "src/services/"
---

# API Conventions
- Always use async/await for API handlers
- Return proper HTTP status codes
```

Rules without `paths:` frontmatter apply globally within the project.

### Guardrail Routing

Learnings with `type: "guardrail"` are special corrections about unwanted behavior. These should be routed to the `## Guardrails` section in CLAUDE.md.

**Guardrail patterns detected by `reflect_utils.py`:**
- "don't add X unless I ask" → `dont-unless-asked`
- "only change what I asked" → `only-what-asked`
- "stop refactoring unrelated code" → `stop-unrelated`
- "don't over-engineer" → `dont-over-engineer`
- "leave X alone" → `leave-alone`
- "minimal changes only" → `minimal-changes`

**When presenting guardrail learnings:**
```
═══════════════════════════════════════════════════════════
GUARDRAIL DETECTED — Constraint about unwanted behavior
═══════════════════════════════════════════════════════════

Original: "don't add docstrings unless I explicitly ask"
Pattern: dont-unless-asked (confidence: 0.90)

Proposed entry for ## Guardrails:
┌────────────────────────────────────────────────────────┐
│ - Don't add docstrings to code unless explicitly asked │
└────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════
```

**Formatting guardrails:**
- Present as constraints/rules rather than preferences
- Use imperative negative form: "Don't X" or "Only do Y when Z"
- Keep concise and actionable
- Route to `## Guardrails` section (create if doesn't exist)

## Size Check

If CLAUDE.md exceeds 150 lines, warn:
```
Note: CLAUDE.md is [N] lines. Consider:
  - /reflect --dedupe to consolidate similar entries
  - /reflect --organize to redistribute across memory tiers
```
