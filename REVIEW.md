# Deep Review — claude-reflect

Date: 2026-07-01. Method: four specialist review passes (Python design via
`codebase-design` deep-module vocabulary; skill craft via `writing-great-skills`;
hook design/security; test coverage + release hygiene), cross-checked, deduped,
and synthesized. The two largest modules were structure-mapped via LSP. All line
numbers reflect the tree at review time.

Severity: **HIGH** (correctness / data loss) · **MED** · **LOW**.

> **Update 2026-07-01 — decisions since review.** Insight I (regex-vs-semantic
> fork) is resolved by [ADR-0001](docs/adr/0001-detection-recall-at-capture-precision-at-process.md):
> **recall at capture, precision at process (inline)**. This retires the
> capture-time precision tables and deletes the subprocess semantic layer, which
> rewrites findings below: **#5 deleted** (not fixed), **#6 moot**, **#8/#9 scope
> shrinks**, **cross-cutting I resolved**. See finding #5 (now "Detection rework")
> for the replacement work item.

---

## Headline

The product promise is "never lose your corrections." The persistence path
(capture → queue → `/reflect`) is the least robust, least tested part of the
codebase. Four independent silent-loss modes converge on that one path, none
covered by a test:

| Mode | Description | Source | Sev |
|------|-------------|--------|-----|
| A | `save_queue` non-atomic `write_text`; a corrupt file reads as `[]`, next save overwrites it → total loss | Python#1 + Hooks#4 | HIGH |
| B | Capture keys the queue off `os.getcwd()`, ignoring the `cwd` in the hook payload → captures land in a folder `/reflect` never scans | Hooks#1 | HIGH |
| C | No lock on read-modify-write; two sessions in one project clobber each other's captures | Python#8 + Hooks#4 | MED |
| D | `load_queue` doesn't check the JSON is a list; `{}` → `AttributeError` → swallowed → capture dropped | Hooks#6 | MED |

Tests concentrate where testing is easy (`detect_patterns`, a pure function,
~135 tests) rather than where risk is high (queue durability, cwd-scoping,
concurrency: zero tests). Coverage is inverted against risk. Fixing the data path
is small: temp-file + `os.replace`, `isinstance(list)` coercion, thread the
payload `cwd` through, one concurrency test.

---

## Must-fix (correctness / data)

1. **Atomic + corruption-safe queue** (A, D) — `scripts/lib/reflect_utils.py:489-500`,
   `load_queue:483-486`. Write to `path.tmp` then `os.replace`; on JSON parse
   failure move the bad file to `learnings-backups/` instead of returning `[]`;
   coerce non-list → `[]`. Hottest path in the system (`capture_learning.py:72-74`).
2. **cwd-scoping** (B) — `capture_learning.py` must read `data.get("cwd")` and
   thread it into `get_queue_path()` / `create_queue_item()` (which today use
   `Path.cwd()` / `os.getcwd()` at `reflect_utils.py:349,790`). Fires in normal
   use (launching from a subdirectory), no error surfaced.
3. **`post_commit_reminder` substring matching** — `post_commit_reminder.py:35`.
   Verified false positives (`echo "...git commit..."`, `grep "git commit"`,
   `git commit-graph`) and a false negative (`--amend` matched inside the commit
   *message*). shlex-tokenize; require adjacent `git commit` argv tokens; test
   `--amend` as a standalone token.
4. **Skill-routing path bug** — `commands/reflect.md:37,969,1337` route skill
   corrections to `commands/*.md`, but a *user's* commands live in
   `.claude/commands/`; `reflect-skills.md:15,281` uses `.claude/commands/`. They
   disagree → skill routing silently no-ops for user commands. Pick one source of
   truth (`.claude/commands/` + `~/.claude/commands/`), align reflect.md + SKILL.md.
5. **Detection rework** (replaces the old "semantic silent-bypass" fix — deleted,
   the subprocess is gone) — per [ADR-0001](docs/adr/0001-detection-recall-at-capture-precision-at-process.md):
   (a) make capture pure recall — retire `FALSE_POSITIVE_PATTERNS`,
   `NON_CORRECTION_PHRASES`, `FORWARD_PIVOT_PATTERNS` (revert PR #37 guard) and
   their branches in `detect_patterns` (`reflect_utils.py:569-642,676-701`);
   (b) delete the subprocess semantic layer on the learning path —
   `validate_queue_items` / `semantic_analyze` in `semantic_detector.py` and
   `/reflect` Step 1.5 (`reflect.md:742-810`), moving precision to inline judgment
   by the `/reflect` agent. Retires the silent-bypass bug by construction (no
   subprocess left to be unavailable). See #6 for the `--scan-history` / `--organize`
   consumers that share the file but are out of ADR-0001 scope.

## Refactoring (structure)

6. ~~**`_call_claude_json()` helper**~~ — **MOOT** per ADR-0001. The triplicated
   subprocess plumbing in `semantic_detector.py` is deleted wholesale by finding #5,
   not refactored. (Note: `validate_tool_error` / `validate_tool_errors` and
   `detect_contradictions` also live in this file and feed `--scan-history` /
   `--organize` — confirm those paths move to inline agent judgment too, or preserve
   just those functions, when executing #5.)
7. **Split `reflect_utils.py`** — LSP-confirmed 9-concern grab-bag (1197 LOC):
   paths, queue I/O + migration, timestamps, pattern tables, `detect_patterns`,
   memory-hierarchy discovery + `suggest_*`, session-JSONL extraction, tool-error
   aggregation. Split → `paths.py`, `queue.py` (co-locate the atomicity fix),
   `patterns.py` (the one genuinely deep sub-module), `memory.py`, `sessions.py`.
   Keep `reflect_utils` as a re-export shim so the many `from lib.reflect_utils
   import …` callers (commands, tests, hooks) don't break.
8. **`detect_patterns` → `NamedTuple`** — `reflect_utils.py:645` returns a bare
   positional 5-tuple unpacked positionally at 2+ call sites; any reorder silently
   corrupts callers. `Detection(type, patterns, confidence, sentiment, decay_days)`,
   zero runtime cost.
9. **One definition of "correction"** — `extract_user_messages(corrections_only=True)`
   (`reflect_utils.py:856-862`) hard-codes its own regex (no CJK) that diverges
   from the `CORRECTION_PATTERNS` tables; `compare_detection.py` has a third.
   `--corrections-only` silently misses every non-English correction. Route
   through a shared predicate. **Scope note (ADR-0001):** the shared predicate is
   now recall-only — precision moved to the inline `/reflect` agent — so "one
   definition" means one wide-net matcher, not one precision-tuned one. CJK
   *precision* patterns stop mattering; keep only CJK *recall* openers.
10. **`load_queue` migration side-effect** — `reflect_utils.py:478`. A function
    named *load* mutates global filesystem state (unlocked read-modify-write across
    every project file) on every hook fire. Make migration an explicit one-shot at
    SessionStart guarded by a sentinel. Removing it also makes `queue.py` pure and
    testable — one change retires three findings (this, concurrency, perf).

## Skill craft (context load)

11. **`reflect.md` sprawl — 540 of 1512 lines (~35%) are flag-branches**
    (`--targets` 136-211, `--review` 213-241, `--dedupe` 243-358, `--organize`
    360-445, `--scan-history` 496-734) that a plain `/reflect` never runs but always
    loads (~5-6K tokens). Extract each to `commands/reflect/<flag>.md`, dispatch via
    context pointers at the top. Single highest-leverage doc change: cuts the
    always-loaded body by a third and removes visible post-completion steps that
    pull the agent toward premature completion. Keep it one `/reflect` (disclosure,
    not new commands — these are flags, not concepts users reach for by name).
12. **Systemic duplication** — the two-stage system, detection patterns, and memory
    hierarchy are each restated across `reflect.md`, `SKILL.md`, `CLAUDE.md`,
    `README`. The "surface everything, never filter" rule appears 4× with escalating
    caps (`reflect.md:557-566,592-598,643-670`) — the signature of fighting
    premature completion with volume, not a lever. Collapse to one leading word
    (*surface, don't suppress*). The semantic-validation procedure is written 3×
    (0.5d/1.5/2e); write once as in-skill reference, point to it.
13. **SKILL.md earns its keep only partially** — now model-invoked, it carries
    permanent context load. The one thing it does that commands can't is
    *autonomously* remind the user to run `/reflect` ("When to Remind Users",
    30-36). That reach justifies the load. Its body (command table, pattern list,
    destinations 20-54) is pure duplication of the commands. Trim to the trigger +
    pointers. Description nit (line 3): front-loads identity that's already in the
    body; keep triggers, and note "captures corrections" is the *hook's* job.
14. **TodoWrite ceremony** — `reflect.md:82-132` spends ~50 lines (prose list +
    the same list again as JSON + "why critical" + workflow rules) restating default
    TodoWrite behavior (no-ops). Collapse to ~5 lines. Same ceremony duplicated in
    `reflect-skills.md:41-59`.

## Cross-cutting insights

- **I. The regex/semantic duality is the core architecture question.** Two
  detectors: cheap regex on every prompt + semantic `claude -p` at `/reflect`.
  Precision already comes from semantic re-validation + `should_include_message`.
  So the regex layer's real job is cheap *recall*; investing regex complexity in
  *precision* (the `FALSE_POSITIVE` / `NON_CORRECTION` / `FORWARD_PIVOT` tables) is
  arguably misplaced — semantic filters that noise anyway. Strategic fork: either
  delete most precision patterns and let regex over-capture (semantic cleans up),
  or drop semantic and commit to regex. Running both and hand-tuning both for
  precision is the costliest option. Decide before adding more patterns. (The
  forward-pivot guard merged from PR #37 pushes toward the regex-precision path —
  worth keeping only if that's the chosen direction.)
  **RESOLVED by [ADR-0001](docs/adr/0001-detection-recall-at-capture-precision-at-process.md):**
  neither run-both nor drop-semantic — **over-capture at regex, filter inline at
  `/reflect`** (not via subprocess `claude -p`). Regex commits to recall; the PR #37
  guard is reverted; the subprocess semantic layer is deleted (see finding #5).
- **II. Duplication is systemic because the docs hand-mirror the code.** Every
  "3 sources of truth" finding has one root: markdown restates what Python already
  encodes (pattern tables, `find_claude_files` types). Real fix is generating the
  doc tables from the code, or reducing every copy to a pointer.
- **III. Coverage is inverted vs. risk.** The library is heavily tested where
  testing is easy (`detect_patterns`); the data-critical, high-frequency path
  (queue durability, cwd-scoping, concurrency) has zero tests. No test simulates
  two sessions writing the queue or the cwd-mismatch bug.
- **IV. Every-prompt cost is real but secondary.** ~18ms/prompt on Linux
  (interpreter + import before `main()` sees even empty stdin), 3-6× on Windows.
  No short-circuit. The SessionStart hook prints a `cleanupPeriodDays` nag every
  session by default (`<= 30` true at the default 30). Cheap wins: gate the nag
  behind a sentinel, gate the capture-echo behind a flag.

## Quick wins

- README badges stale: `2.6.0` / `160 tests` vs actual `3.1.0` / `227`
  (`README.md:4,6`). RELEASING.md steps 1 & 3 not executed.
- `DISTRIBUTION.md` (maintainer submission tracker + marketing copy) ships to end
  users — move to `.github/` or gitignore.
- CLAUDE.md says "Python 3.6+", CI floor is 3.8 — reconcile.
- `scripts/legacy/*.sh` are **not** dead — they're the differential-test oracle in
  `test_integration.py`. Keep; add a coupling comment so nobody deletes them.
- Typing modernization: `List/Dict/Optional/Tuple` → builtin generics (basedpyright
  warns across both lib files).
- `session_start_reminder.py` has zero test coverage anywhere (the only hook
  entrypoint exercised by nothing) — add a subprocess test to `test_integration.py`.
- ~~`semantic_detector` live `claude -p` contract untested~~ — **MOOT** per ADR-0001;
  the subprocess layer is deleted (finding #5). Its ~50 mocked tests go with it.

## Non-findings (verified — don't chase)

- Security is clean: no `shell=True` / `eval`, no injection surface in
  `post_commit_reminder` (inspects only), backups under `~/.claude/learnings-backups/`
  not `/tmp`.
- Hook entrypoints ARE covered via `test_integration.py` subprocess runs + CI smoke.
- No `AGENTS.md` in-repo is correct — it's a user-project sync *target*, not a repo
  artifact.
- The functions that looked dead (`get_backup_dir`, `append_to_queue`,
  `suggest_claude_file`, etc.) all have real callers.

## Suggested sequence

1. Persistence layer (must-fix 1, 2, + list-coercion) — protects the product
   promise, smallest change, add one concurrency test. Independent of detection.
2. ~~Decide insight I~~ — **DONE** ([ADR-0001](docs/adr/0001-detection-recall-at-capture-precision-at-process.md)).
3. Detection rework (must-fix 5) — retire capture-time precision tables + delete
   the subprocess semantic layer; precision moves inline to `/reflect`. Folds in
   #6 (moot), #9 (recall-only predicate), cross-cutting I. Do after step 1 so the
   queue durability fix lands before the queue gets noisier.
4. `reflect.md` sprawl extraction (skill 11) — biggest context-load win. Note the
   deleted Step 1.5 (from step 3) already removes one always-loaded block.
5. Split `reflect_utils.py` (refactor 7) behind a re-export shim.
