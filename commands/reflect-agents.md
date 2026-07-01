---
description: Discover delegatable subagent roles from recurring tool-call shapes
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList, TaskGet
---

## Arguments
- `--days N`: Analyze sessions from last N days (default: 14).
- `--project <path>`: Analyze a specific project (default: current project).
- `--all-projects`: Analyze ALL projects (cross-project sweep). A role recurring
  across many repos is flagged as a **global-agent** candidate.
- `--dry-run`: Propose roles only; write no agent files.

## Context
- Current project: !`pwd`
- Session files location: `~/.claude/projects/`
- Project agents: `.claude/agents/` · Global agents: `~/.claude/agents/`

## Your Task

Discover **delegatable roles** — recurring *sub-work shapes* you keep performing
inline that a focused specialist subagent should own — and propose ready-to-use
agent definition files. This is the sibling of `/reflect-skills` (ADR-0003):

- `/reflect-skills` keys off the repeated **top-level user request**.
- `/reflect-agents` keys off the repeated **tool-call shape** — e.g. a
  `Grep→Read→Grep` code-hunting cluster that recurs across *varied* tasks. This is
  a signal `/reflect-skills` structurally cannot see.

**Human-in-the-loop throughout.** You propose; the user approves role name,
description, tool scope, and location before any file is written.

---

## Workflow

### Step 1: Initialize Task Tracking

Use **TaskCreate** to register the phases and **TaskUpdate** each as you go:
parse arguments → gather tool-sequence data → check existing agents → analyze for
roles → propose candidates → assign locations → get approval → generate agent
files → validate.

### Step 2: Parse Arguments

`--days N` (default 14), `--project <path>`, `--all-projects`, `--dry-run`.
Default: current project only unless `--all-projects`.

### Step 3: Gather Tool-Sequence Data (pass-1, mechanical)

**DO NOT parse session JSONL by hand.** Use the plugin's extractor — it strips the
bulky tool inputs and emits compact tool-name sequences with occurrence counts and
the observed tool set (the token-bounded pass-1 for this command):

```bash
# Current project (default):
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_tool_sequences.py" \
  --project "$(pwd)" --min-count 2

# Cross-project sweep (--all-projects):
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_tool_sequences.py" \
  --all --min-count 3
```

Output is JSON clusters:
`[{"sequence": ["Grep","Read","Grep"], "count": N, "tools": ["Grep","Read"], "projects": ["-a","-b"], "seen_in_projects": M}, ...]`.
`seen_in_projects`/`projects` carry each shape's **cross-project reach** — the
signal for global-vs-local routing (Step 5b). `--days` defaults to 14 (0 = no
limit) and reuses the same shared walk as `/reflect --all-projects`.

**Also gather user delegation-language** — role-verbs that signal explicit
delegation intent ("go find…", "review…", "investigate…", "check whether…"). These
BOOST a role proposal. Extract user messages with the existing script:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_session_learnings.py" "$SESSION_FILE"
```

### Step 3b: Check Existing Agents (dedup)

Before proposing, discover what already exists so you don't duplicate:

```bash
ls .claude/agents/*.md 2>/dev/null | xargs -I{} basename {} .md
ls ~/.claude/agents/*.md 2>/dev/null | xargs -I{} basename {} .md
```

**Known-roles guard** (curated — ecosystem agents with no stable file to dedup
against). If a discovered role matches one of these, surface it as "likely covered
— skip?" rather than auto-proposing a duplicate:

| Discovered role shape | Likely covered by |
|-----------------------|-------------------|
| Locate code / find where X is (`Grep`/`Glob`/`Read` hunting) | `Explore` |
| Open-ended multi-step research | `general-purpose` |
| Review a diff / audit changes (`Read`+`Bash git diff`) | `code-reviewer` |

> This list is curated and small — expect it to need occasional updates as the
> ecosystem's common agents change.

### Step 4: Analyze for Delegatable Roles (AI-powered)

Reason over the tool-sequence clusters — do NOT keyword-match. A role-worthy
pattern is a **recurring cluster of tool calls that recurs across varied top-level
tasks** — a stable shape of delegated sub-work, independent of the surrounding
request. For each candidate role, determine:

1. **The shape** — which tool-name sequence(s) form the cluster. Exact-match counts
   from pass-1 will mostly be small; YOU cluster semantically (e.g.
   `Grep,Read`, `Grep,Read,Grep`, `Glob,Read` are all the same *locator* role).
2. **Evidence-scoped tools** — the union of the observed `tools` sets of the
   clusters that make up the role. This IS the least-privilege `tools` allowlist
   (ADR-0003 decision 2) — a locator gets `Grep, Read, Glob`; a reviewer gets
   `Read, Bash`. Never propose open/all tools.
3. **Delegation-language boost** — did the user use role-verbs around this shape?
4. **Cross-project reach** (`--all-projects`) — does the shape appear in sessions
   from ≥2 distinct project folders? If so it is a **global** candidate.

> **Be skeptical of shapes that mirror existing subagents.** The `--all` sweep
> includes `agent-*.jsonl` subagent transcripts — already-delegated work. An
> `Explore` subagent's `Grep→Read` calls will look like a fresh "locator role".
> Beyond the known-roles guard, discount clusters whose shape simply reproduces
> what an existing/ecosystem subagent already does; propose a role only when it is
> genuinely un-owned sub-work you keep doing *inline*.

### Step 5: Propose Role Candidates

```
════════════════════════════════════════════════════════════
DELEGATABLE ROLES DISCOVERED
════════════════════════════════════════════════════════════

Likely covered by existing/ecosystem agents (skip?):
- locator → covered by `Explore`

NEW role candidates:

1. test-writer   (Confidence: High)   [project: myapp]
   → When to delegate: writing/updating unit tests for a changed module
   Shape: Read → Write → Bash(pytest)  ×7
   Proposed tools: Read, Write, Bash
   Delegation language seen: "write tests for…" ×3

2. dependency-auditor   (Confidence: Medium)   [GLOBAL — spans 3 repos]
   → When to delegate: checking a dependency's version/usage across the repo
   Shape: Grep → Read → Bash(cat package.json)  ×5
   Proposed tools: Grep, Read, Bash
════════════════════════════════════════════════════════════
```

If every discovered role matches an existing/known agent, say so and stop:
> "All discovered roles are already covered by existing or ecosystem agents."

Use **AskUserQuestion**: which roles to create? name changes? tool-scope
adjustments? any to skip?

### Step 5b: Assign Locations

- Evidence from ONE project → that project's `.claude/agents/`.
- Evidence spans MULTIPLE projects (or `--all-projects` with cross-repo reach) →
  global `~/.claude/agents/`.
- Confirm with **AskUserQuestion** before writing.

### Step 6: Generate Agent Files

> **`--dry-run` stops here** — show the proposed frontmatter + system prompt for
> each role and write nothing.

For each approved role, write a well-formed agent file. **`tools` = the
evidence-scoped set** (Step 4.2), never open/all.

```markdown
---
name: [role-name]
description: [When to delegate — the trigger, e.g. "Use when writing or updating
  unit tests for a changed module. Reads the module, writes tests, runs them."]
tools: [Comma, Separated, Evidence-Scoped, Tools]
---

You are a [role] specialist. [Synthesized system prompt describing the role's
job, derived from the observed sub-work shape.]

## What you do
1. [First step of the observed shape]
2. [Second step]
3. [Third step]

## Constraints
- Stay within your tool allowlist.
- [Any guardrails inferred from delegation language or corrections.]
```

Write to:
- Project: `[project-path]/.claude/agents/[role-name].md` (mkdir -p first)
- Global: `~/.claude/agents/[role-name].md`

### Step 6b: Validate

For each generated file:

```bash
ls -la [path]/.claude/agents/[role-name].md
head -5 [path]/.claude/agents/[role-name].md   # frontmatter parses
```

Confirm the `tools` line lists only resolvable tool names (the evidence-scoped
set). Then inform the user:
> "Agent created. Restart Claude Code or start a new conversation to use it."

### Step 7: Summary

```
════════════════════════════════════════════════════════════
AGENT GENERATION COMPLETE
════════════════════════════════════════════════════════════
Created [N] agent(s):
  Project myapp:  test-writer      (.claude/agents/test-writer.md)
  Global:         dependency-auditor (~/.claude/agents/dependency-auditor.md)
════════════════════════════════════════════════════════════
```

---

## Key Principles

1. **Sub-work shape, not request** — the signal is the recurring tool-call cluster.
2. **Least-privilege from evidence** — `tools` = observed footprint, never open.
3. **Dedup hard** — file-based agents + the known-roles guard (don't reinvent `Explore`).
4. **Human-in-the-loop** — approve name/description/tools/location before writing.
5. **Cross-project = global** — a role spanning repos earns `~/.claude/agents/`.
