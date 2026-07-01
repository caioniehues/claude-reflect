# /reflect --all-projects — global harvest

Disclosed reference for `/reflect`. Read when the user passes `--all-projects`.
Sweeps session history across **every** `~/.claude/projects/<encoded>/` folder,
dedupes corrections cross-project, and surfaces the ones worth promoting to global
`~/.claude/CLAUDE.md` — ranked by how many projects each recurred in (ADR-0002).

**Self-sufficient flag.** `--all-projects` implies `--scan-history` and forces
`global` scope. It replaces the per-project Step 0.5 scan; it does NOT drain the
per-project queue (history-only). Composes with `--days N` and `--dry-run`.
`--scan-history --all-projects` is identical to `--all-projects` alone.

**Operating principle — surface, don't suppress.** Global-worthy candidates are
actionable. Project-specific corrections found along the way are *listed* per
project with counts and a nudge to run `/reflect --scan-history` there — never
silently dropped (ADR-0001 / ADR-0002 point 4).

**Only write target: global `~/.claude/CLAUDE.md`.** This mode never writes into
any other repo's tree — routing is cwd-relative and a sweep cannot safely edit
repos the user isn't in. Do not touch project `./CLAUDE.md`, subdir files, or rule
files here.

## a. Run pass-1 (mechanical sweep)

Pass 1 is a bounded **script** — it walks all projects, applies the recall
predicate, dedupes across projects, and returns only a distilled shortlist. It
does NOT load raw sessions into your context (token bound — cost scales with
distinct candidates, not total history).

```bash
# Default window is 90 days; pass the user's --days N through (0 = no limit).
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scan_all_projects.py" --days 90
```

> Note: `--all-projects` defaults `--days` to **90**, whereas per-project
> `--scan-history` defaults to 30 — a wider window is intentional for a one-shot
> cross-project harvest. This is not a bug.

The script prints JSON:

```json
{
  "global_candidates": [
    {"learning": "no, use pnpm not npm", "seen_in_projects": 5,
     "projects": ["-a", "-b", ...], "occurrences": 7, "normalized": "..."}
  ],
  "project_specific": {
    "-home-bob-repo-x": {"count": 4, "samples": ["...", "..."]}
  },
  "projects_scanned": 30
}
```

## b. Pass-2: judge the shortlist inline (precision)

You are the model in the loop (ADR-0001 — no subprocess, no `claude -p`). For each
entry in `global_candidates`, judge reusability inline exactly as in
`scan-history.md` §d:

- **Reject only** bare questions, pure task confirmations, or too-vague-to-extract.
- **Accept** anything mentioning tools/tech/API names, flags/settings, best
  practices, model names/versions, timing, or env setup.
- **Trust** user corrections for model names, API versions, tool availability, and
  flag values — do not try to validate whether something "exists".

**Bias toward `global`.** Cross-project frequency is the strongest proxy for
global-worthiness: `seen_in_projects >= 2` is already a strong global signal, and
the list is pre-ranked by it. For each accepted candidate produce an actionable
imperative learning ("Use pnpm, not npm, for package installs") with scope
`global`.

## c. Present the harvest (surface, don't suppress)

```
═══════════════════════════════════════════════════════════
GLOBAL HARVEST — swept [N] projects
═══════════════════════════════════════════════════════════

GLOBAL CANDIDATES (ranked by cross-project frequency):

#1  seen in 5 projects
    "no, use pnpm not npm"
    → Proposed (global): Use pnpm, not npm, for package installs

#2  seen in 2 projects
    "actually prefer ripgrep"
    → Proposed (global): Prefer ripgrep (rg) over grep for code search

───────────────────────────────────────────────────────────
PROJECT-SPECIFIC (not actionable here — belongs to that repo):

  -home-bob-repo-x   4 corrections   → run `/reflect --scan-history` there
  -home-bob-repo-y   2 corrections   → run `/reflect --scan-history` there
═══════════════════════════════════════════════════════════
```

Use **AskUserQuestion** to let the user select which global candidates to write.

## d. Apply (or preview with --dry-run)

- **`--dry-run`:** show the harvest and the exact lines that WOULD be appended to
  `~/.claude/CLAUDE.md`, then stop. Write nothing. End with:
  "Dry run complete. Run /reflect --all-projects without --dry-run to apply."
- **Otherwise:** append each approved learning to global `~/.claude/CLAUDE.md`
  (dedupe against existing entries first — read the file, skip anything already
  present or clearly equivalent). Confirm what was written.

Never write to any file other than `~/.claude/CLAUDE.md` in this mode.
