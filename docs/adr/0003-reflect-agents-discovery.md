---
status: accepted
---

# Agent discovery: `/reflect-agents`

A sibling to `/reflect-skills`. Where `/reflect-skills` discovers repeated
*top-level user workflows* and proposes command files, `/reflect-agents` discovers
recurring **delegatable roles** and proposes subagent definitions. It must not be
`/reflect-skills` with a different output path — it needs its own signal and its
own value.

## Decision

1. **Signal = recurring sub-work shape, boosted by delegation language.** An
   agent-worthy pattern is a recurring *cluster of tool calls* (e.g.
   `Grep→Read→Grep` code-hunting) that recurs across *varied* top-level tasks —
   a stable shape of delegated sub-work, independent of the surrounding request.
   Skills key off the repeated *request*; agents key off the repeated *sub-work
   shape*. User role-verbs ("go find…", "review…", "investigate…") boost detection.
2. **Generate a full agent file with evidence-scoped tools.** Emit a complete
   agent `.md` (frontmatter `name` / `description` = when-to-delegate / `tools` /
   optional `model`, plus a synthesized system prompt). The `tools` allowlist is
   **derived from the observed tool footprint** of that role's clusters — the
   locator gets `Grep, Read, Glob`; the reviewer gets `Read, Bash`. Least-privilege
   from ground truth is the feature's standout property; `/reflect-skills` cannot
   do it.
3. **Dedup = file-based + known-roles guard.** Skip roles already defined in
   `.claude/agents/` / `~/.claude/agents/`. Additionally carry a curated guard over
   common ecosystem agents with no stable file location (`Explore`=locate,
   `general-purpose`=research, `code-reviewer`=review) and surface a match as
   "likely covered by `Explore` — skip?" rather than auto-proposing a duplicate.
4. **Output location mirrors `/reflect-skills`.** Project `.claude/agents/` by
   default; global `~/.claude/agents/` for roles whose evidence spans projects.
5. **Compact-sequence extraction (two-pass, token bound).** A new mechanical
   extractor (`extract_tool_sequences` in the `sessions` layer) parses assistant
   `tool_use` blocks and emits distilled **tool-name sequences** per task —
   `Grep,Read,Grep` with occurrence counts and the observed tool *set* — while
   **stripping the bulky tool inputs**. Only the distillate reaches the agent
   (pass 2), which names roles over it. The recorded tool-set per cluster *is* the
   evidence-scoped `tools` allowlist (decision 2), so auto-scoping is a direct
   byproduct of pass 1, not a guess. Mirrors ADR-0002's two-pass shape.

## Considered and rejected

- **Signal = same as reflect-skills** (emit an agent instead of a command).
  Rejected: no new signal → structurally duplicates `/reflect-skills`.
- **Open `tools`** (unset allowlist, inherit all). Rejected: discards the
  evidence-derived least-privilege footprint that justifies the feature.
- **Propose-only, no file generation.** Rejected: loses the auto-scoped-tools
  value; leaves the tedious part to the user.
- **File-only dedup / no dedup.** Rejected: would confidently propose an
  "investigator" that duplicates the ecosystem's `Explore`.

## Consequences

- **Depends on ADR-0002's shared cross-project machinery** (built first). A role
  recurring across many repos → recommend a **global** agent; single-repo →
  project-local. Cross-project frequency is as strong a signal for roles as for
  learnings.
- **New extraction capability:** role detection reads *assistant tool_use
  sequences* from session JSONL, which today's extraction (user-message-only) does
  not surface. The `sessions` layer gains `extract_tool_sequences` (decision 5) —
  the main new build in this feature.
- Human-in-the-loop throughout (mirrors `/reflect-skills`): user approves roles,
  names, tool scopes, and locations before any file is written.
