# /reflect --organize

Disclosed reference for `/reflect`. Read only when the user passes `--organize`.
Analyze the full memory hierarchy and suggest reorganization to reduce clutter
and improve routing, then exit without processing the queue.

**1. Inventory all memory locations:**
```python
from scripts.lib.reflect_utils import find_claude_files, read_auto_memory, read_all_memory_entries

files = find_claude_files()
auto_memory = read_auto_memory()
all_entries = read_all_memory_entries()
```
Count lines, entries, and files for each tier.

**2. Detect issues:**

| Issue | Detection | Fix |
|-------|-----------|-----|
| Overgrown file (>150 lines) | Line count check | Split into rule files or subdirectory CLAUDE.md |
| Wrong-tier entries | Global-looking entries in project file or vice versa | Move to correct tier |
| Scattered topics | Same topic across multiple files | Consolidate into rule file |
| Path-scoping opportunities | Entries mentioning specific directories | Create path-scoped rule files |
| Auto memory promotion candidates | Confirmed patterns in auto memory | Promote to CLAUDE.md |
| Cross-tier duplicates | Same entry in multiple tiers | Remove duplicates |

**3. Present findings:**
```
════════════════════════════════════════════════════════════
MEMORY HIERARCHY ANALYSIS
════════════════════════════════════════════════════════════

Current state:
  ~/.claude/CLAUDE.md          182 lines  ⚠️ (over 150)
  ./CLAUDE.md                   95 lines  ✓
  .claude/rules/                 0 files
  Auto memory                    2 files

Issues found: 4
────────────────────────────────────────────────────────────

#1 OVERGROWN: ~/.claude/CLAUDE.md (182 lines)
   → Suggestion: Extract model preferences to ~/.claude/rules/model-preferences.md
   → Suggestion: Extract guardrails to .claude/rules/guardrails.md

#2 WRONG TIER: 3 global-looking entries in ./CLAUDE.md
   → "Always use venv" — should be in ~/.claude/CLAUDE.md
   → "Never use force push" — should be in ~/.claude/CLAUDE.md

#3 PROMOTION: 2 auto memory entries confirmed across sessions
   → "Use batch mode for API calls" — promote to ./CLAUDE.md

#4 DUPLICATE: 1 entry found in multiple tiers
   → "Use gpt-5.1 for reasoning" in both ~/.claude/CLAUDE.md and auto memory

════════════════════════════════════════════════════════════
```

**4. Get user approval per fix** with AskUserQuestion (extract / skip).

**5. Apply reorganization** with the Edit tool: move content between files, create
new rule files as needed, remove duplicates from source files, preserve section
structure in all files.

**6. Exit after reorganization (don't process queue).**
