# CONTEXT

Domain model for claude-reflect. Terms are the project's ubiquitous language;
decisions of record live in `docs/adr/`.

## Established terms

- **Learning** — a durable, reusable statement extracted from a correction and
  written into a memory tier. Carries a **scope** (`global` | `project`).
- **Capture** — the always-on hook stage that queues correction-shaped prompts
  (wide **recall** net; see ADR-0001).
- **Process** — the `/reflect` stage: human-reviewed **precision**, judged inline.
- **Memory tier** — a destination file: global `~/.claude/CLAUDE.md`, project
  `./CLAUDE.md`, `CLAUDE.local.md`, subdir CLAUDE.md, rule files, auto memory.
- **Scan-history** — mining a project's session `*.jsonl` for corrections the
  hooks missed (`/reflect --scan-history`), per-project today.
- **Skill discovery** — `/reflect-skills`: AI-powered discovery of repeated
  *top-level user workflows* → proposes command files.

## Feature terms (ADR-0002/0003, accepted — shipped in #12)

### Cross-project global harvest (`/reflect --all-projects`, ADR-0002)

- **Cross-project scan** — sweeping session history across *every*
  `~/.claude/projects/<encoded>/` folder, not just the current project's.
- **Global harvest** — the only output of `--all-projects`: learnings worth
  promoting to global `~/.claude/CLAUDE.md`. Project-scoped learnings from other
  repos are *listed* (surface, don't suppress) but not actionable here, because
  `/reflect` writes relative to cwd and cannot safely edit other repos' trees.
- **Global-worthiness** — the bar a candidate must clear to be actionable in
  harvest mode: true across projects, not repo-specific.
- **Cross-project frequency** — how many distinct projects a deduped learning
  appears in. The strongest available proxy for global-worthiness; drives ranking
  and biases the inline judge toward `global`. ("Use pnpm" in 5 repos → global.)

### Agent discovery (`/reflect-agents`, ADR-0003)

- **Sub-work shape** — a recurring *cluster of tool calls* (e.g. `Grep→Read→Grep`
  code-hunting) that recurs across varied top-level tasks. The signal that a
  **delegatable role** exists — distinct from a skill's *repeated user request*.
- **Delegatable role** — a coherent specialist the main agent keeps performing
  inline and would offload to a subagent (locator, reviewer, test-writer).
- **Delegation language** — user role-verbs ("go find…", "review…",
  "investigate…") that boost detection of a role.
- **Evidence-scoped tools** — the subagent's `tools` allowlist derived from the
  *observed* tool footprint of its clusters: least-privilege from ground truth.
- **Known-roles guard** — a curated check that skips roles already covered by
  ecosystem agents (`Explore`=locate, `general-purpose`=research,
  `code-reviewer`=review) that have no stable file location to dedup against.

## Shared machinery (ADR-0002 + ADR-0003)

The cross-project sweep (iterate all `~/.claude/projects/*`, extract per project,
dedup with cross-project frequency) is built once as a `sessions`-layer helper and
consumed by both features. `/reflect --all-projects` (learnings) lands first;
`/reflect-agents` (roles) builds on the same core, inheriting `--all-projects` and
frequency-weighting. Consistent with the #8 split's intent: no duplicated logic.
