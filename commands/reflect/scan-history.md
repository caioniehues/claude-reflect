# /reflect --scan-history

Disclosed reference for `/reflect`. Read when the user passes `--scan-history`
(or accepts the first-run scan offer). Scans past sessions for corrections the
hooks missed — useful for cold-start installs and periodic deep review. The
**surface, don't suppress** operating principle governs everything here.

Results are ADDED to the working list alongside queue items; continue to Step 3
(Project-Aware Filtering) with the combined list.

## a. Find ALL session files for this project

1. List project folders to find the path pattern:
   ```bash
   ls ~/.claude/projects/ | grep -i "$(basename $(pwd))"
   ```
2. **Underscores vs hyphens:** directory names may use underscores (`darwin_new`)
   but encoded paths use hyphens (`darwin-new`). If the first grep fails, retry:
   ```bash
   ls ~/.claude/projects/ | grep -i "$(basename $(pwd) | tr '_' '-')"
   ```
3. List ALL session files in that folder:
   ```bash
   ls ~/.claude/projects/[PROJECT_FOLDER]/*.jsonl
   ```

Note: project paths have `/` replaced with `-`. For `/Users/bob/code/myapp`, look
for `-Users-bob-code-myapp`.

Process ALL session files (not just recent): main UUID-named files AND
`agent-*.jsonl` files. Apply the `--days N` filter by file modification time if
specified.

## b. Extract corrections from session files

Session files are JSONL. Extract user messages, then match correction patterns —
use Read, Grep, or Bash+jq, whatever works.

**CRITICAL:** filter out command expansions with `isMeta != true`. Command
expansions (like /reflect itself) carry documentation text that causes false
positives.

**Language-aware patterns:** sample a few user messages to detect the language;
if non-English, add its patterns:

| Language | Example patterns to add |
|----------|------------------------|
| Russian | `нет,? используй\|не используй\|на самом деле\|запомни:\|лучше\|предпочитаю` |
| Spanish | `no,? usa\|no uses\|en realidad\|recuerda:\|prefiero\|siempre usa` |
| German | `nein,? verwende\|nicht verwenden\|eigentlich\|merke:\|bevorzuge\|immer` |

Default English patterns: `remember:`, `no, use`, `don't use`, `actually`,
`stop using`, `never use`, `that's wrong`, `I meant`, `use X not Y`.

Extract two things:
1. **User messages** with correction patterns (`type: "user"`, `isMeta != true`).
2. **Tool rejections** — `toolUseResult` fields containing "user said:" followed
   by feedback. "user said:" with empty content = rejection without feedback, skip.
   Tool rejections are high-signal corrections; per the operating principle,
   always surface them.

Key structure:
- User messages: `{"type": "user", "message": {"content": [{"type": "text", "text": "..."}]}}`
- Tool rejections: `{"toolUseResult": "The user doesn't want to proceed\nuser said:\n[feedback]"}`

## c. Apply date filter if `--days N` specified

Check file modification time; skip files older than N days.

## d. Judge reusability inline

Judge each extracted correction inline (ADR-0001 — no subprocess, no `claude -p`;
you are the model in the loop). This works in any language. For borderline items,
default to **surface, don't suppress**: include and let the user decide.

**Reject only** a bare question (ends with "?"), pure task confirmation ("yes",
"ok", "done", "looks good"), or something too vague to extract meaning ("fix it").

**Accept** anything mentioning: tool/technology/API names or parameters; flags,
settings, or config ("enable X", "use flag Y"); best practices ("always do X");
model names or versions; rate limits/delays/timing; file paths or env setup.

**Trust user corrections** for model names, API versions, tool availability, and
flag/parameter values — the user has more current knowledge than training data.
Do NOT try to validate whether something "exists" or is "correct".

**Borderline → get context first.** If a correction seems context-specific ("please
enable that flag"), search surrounding messages to learn WHICH flag — these are
often reusable API-parameter learnings.
```bash
grep -n "enable that flag" "$SESSION_FILE" | head -1
```

For each accepted correction, create: an actionable learning in imperative form
("Use gpt-5.1 for reasoning tasks"), a suggested scope ("global" or "project"),
and the actual parameter/value when possible.

## e. Deduplicate

Collect accepted corrections; remove exact duplicates; for similar corrections,
keep the most recent.

## f. Build working list

- ADD history-scan results to the working list (alongside queue items).
- Use the actionable learning you created as the proposed entry, the scope
  suggestion as the default, and mark source `history-scan` or `tool-rejection`.

**Sanity check:** if the queue had N items, the working list must still have at
least N — if it went empty while the queue was not, re-add the queue items.

**Presentation (surface, don't suppress):** if extraction found ANY matches, show
the top 10-15 raw matches for review and let the user select which to keep. Never
conclude "0 learnings found" while grep returned matches or tool rejections went
unshown.
```
═══════════════════════════════════════════════════════════
RAW MATCHES FOUND — [N] items need review
═══════════════════════════════════════════════════════════

#1 [source: session-scan | tool-rejection]
   "[raw text from extraction]"
   → Proposed: [actionable learning] | Scope: [global/project]

#2 ...
═══════════════════════════════════════════════════════════
```

## g. Extract tool execution errors (project-specific only)

Scan session files for REPEATED tool execution errors (`is_error: true`) that
reveal project-specific context — connection errors, module-not-found,
env-undefined, service-specific errors (Supabase/Postgres/Redis).

**Exclude:** Claude Code guardrails ("File has not been read yet", "exceeds max
tokens"), global Claude behavior (bash quoting, EISDIR), and one-off errors (keep
only patterns with 2+ occurrences).

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/extract_tool_errors.py" --project "$(pwd)" --min-count 2 --json
```
Or use the utilities directly:
```python
from lib.reflect_utils import extract_tool_errors, aggregate_tool_errors
from lib.semantic_detector import validate_tool_errors

errors = []
for session_file in session_files:
    errors.extend(extract_tool_errors(session_file, project_specific_only=True))
aggregated = aggregate_tool_errors(errors, min_occurrences=2)
validated = validate_tool_errors(aggregated)   # optional
```

Add validated error patterns to the working list: mark source `tool-error`, use
`suggested_guideline`/`refined_guideline` as the proposed entry, scope `project`.
```
═══════════════════════════════════════════════════════════
TOOL ERROR PATTERNS — [N] project-specific issues found
═══════════════════════════════════════════════════════════

#1 [connection_refused] — 5 occurrences
   Sample: "Connection refused to localhost:5432"
   → Proposed: "Check DATABASE_URL in .env for PostgreSQL connection"

#2 [env_undefined] — 3 occurrences
   Sample: "SUPABASE_URL is not defined"
   → Proposed: "Load .env file before accessing environment variables"
═══════════════════════════════════════════════════════════
```
