---
status: accepted
---

# Cross-project scan: global harvest via `/reflect --all-projects`

`/reflect --scan-history` mines one project's session history for missed
corrections. A **cross-project** scan — mining every `~/.claude/projects/*` folder
at once — is desirable because durable, everywhere-true preferences ("use pnpm
not npm") often get stated in one repo but belong to *all* of them. The design
tension is that routing is cwd-relative (`find_claude_files`, per-learning
`global | project` scope), so a sweep cannot safely write project-scoped learnings
into repos the user isn't in.

## Decision

`/reflect --all-projects` is a **global harvest**:

1. **Global-only output.** It surfaces and writes only learnings worth promoting
   to global `~/.claude/CLAUDE.md`. It never writes into other repos' trees.
2. **History-only input.** It deep-mines each project's session `*.jsonl`. It does
   not drain per-project queues — those are already surfaced by plain `/reflect`
   in that repo, and folding them in would double-handle and muddy the model.
3. **Self-sufficient flag.** `--all-projects` *implies* `--scan-history` (the only
   input mode) and *forces* global scope. Mirrors `/reflect-skills --all-projects`.
   Composes with `--days N`. `--scan-history --all-projects` is harmless (same result).
4. **Surface, don't suppress.** Global-worthy candidates are actionable; project-
   specific corrections found along the way are *listed* per project with counts
   ("not actionable here — belongs to `<project>`; run `/reflect --scan-history`
   there"), never silently dropped. Honors the ADR-0001 operating principle.
5. **Frequency-weighted dedup.** Deduped candidates carry **cross-project
   frequency** (`seen in N projects`). Recurrence across ≥2 projects is the
   strongest proxy for global-worthiness — it ranks candidates and biases the
   inline judge toward `global`. This is the capability a per-project loop cannot
   provide, and the reason the mode earns its existence.
6. **Two-pass, mechanical-then-agent (token bound).** Pass 1 is a *script* that
   walks every project, applies the recall predicate (`is_correction_candidate`),
   and aggregates + dedups + counts cross-project frequency **without** loading raw
   sessions into the agent. Pass 2 hands the `/reflect` agent only the deduped,
   frequency-ranked **shortlist** for inline judgment. Cost scales with distinct
   candidates, not total history — essential when "all projects" is unbounded. A
   default `--days 90` window is a coarse pre-filter. The agent still owns all
   precision/judgment; the script only distills.

## Considered and rejected

- **Full per-project processing** (write each repo's project-scoped learnings into
  its own `./CLAUDE.md`). Rejected: writes into many repos the user isn't in,
  dirties working trees, risks touching repos mid-work — a footgun.
- **Queues-only / both** input. Rejected: per-project queues already surface via
  plain `/reflect`; double-handling muddies the mental model.
- **Higher-bar filter that hides project-specific items.** Rejected: violates
  surface-don't-suppress — you'd never learn a repo has rich local learnings.
- **Plain dedup / no dedup.** Rejected: discards cross-project frequency, the one
  signal that distinguishes this mode from looping `/reflect` per repo.

## Consequences

- A shared `sessions`-layer helper ("yield extracted corrections per project across
  `~/.claude/projects/*`, deduped with frequency") is introduced as the **pass-1**
  mechanical core and reused by `/reflect-agents` (ADR-0003). Build once; DRY per
  the #8 split intent.
