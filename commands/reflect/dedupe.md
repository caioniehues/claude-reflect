# /reflect --dedupe

Disclosed reference for `/reflect`. Read only when the user passes `--dedupe`.
Scan existing CLAUDE.md files for similar entries AND contradictions, then exit
without processing the queue.

**1. Read both CLAUDE.md files:**
```bash
cat ~/.claude/CLAUDE.md
cat CLAUDE.md 2>/dev/null
```

**2. Extract all bullet points:** lines starting with `- ` under section headers. Track line numbers.

**3. Detect contradictions using semantic analysis:**
```python
from lib.semantic_detector import detect_contradictions

entries = [...]  # List of bullet point strings from both files
contradictions = detect_contradictions(entries)
# Returns: [{"entry1": "...", "entry2": "...", "conflict": "reason"}]
```

**4. Analyze for semantic similarity:** group entries that reference the same
tool/model/concept, give overlapping advice, or could be merged without losing
information.

**5. Present findings:**
```
═══════════════════════════════════════════════════════════
CLAUDE.MD DEDUPLICATION SCAN
═══════════════════════════════════════════════════════════

⚠️ CONTRADICTIONS FOUND (2)
────────────────────────────────────────────────────────────

#1: Conflicting indentation preferences
    Line 12: "- Use tabs for indentation"
    Line 78: "- Use spaces for indentation"
    Conflict: opposite indentation preferences

#2: Conflicting model recommendations
    Line 24: "- Use gpt-5.1 for all tasks"
    Line 89: "- Prefer Claude for reasoning tasks"
    Conflict: different model preferences for similar tasks

────────────────────────────────────────────────────────────

SIMILAR ENTRIES (2 groups)
────────────────────────────────────────────────────────────

Group 1 (Global CLAUDE.md):
  Line 45: "- Use gpt-5.1 for complex tasks"
  Line 52: "- Prefer gpt-5.1 for reasoning"
  → Proposed: "- Use gpt-5.1 for complex reasoning tasks"

Group 2 (Project CLAUDE.md):
  Line 12: "- Always use venv"
  Line 28: "- Create virtual environment for Python"
  → Proposed: "- Use venv for Python projects"

────────────────────────────────────────────────────────────
Unique entries: 23 (no changes needed)
═══════════════════════════════════════════════════════════
```

**6. Handle contradictions with AskUserQuestion** — one question per contradiction,
options: keep first / keep second / merge / keep both.

**7. Handle similarity groups with AskUserQuestion** — options: apply all
consolidations / review each group / cancel.

**8. Apply changes** with the Edit tool: resolve contradictions per user choice,
replace redundant entries with consolidated versions, remove duplicate lines,
preserve section structure.

Exit after deduplication (don't process queue).
