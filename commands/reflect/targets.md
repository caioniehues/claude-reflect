# /reflect --targets

Disclosed reference for `/reflect`. Read only when the user passes `--targets`.
Detect and display all AI assistant config files with **line counts** and
**size warnings**, then exit without processing learnings.

**Line Count Threshold:** 150 lines (frontier models handle ~150-200 instructions reliably).

**Detection steps:**

1. Find all memory tier files using `find_claude_files()` (discovers CLAUDE.md, CLAUDE.local.md, rule files)
2. Count lines in each file
3. Check for auto memory directory
4. Display with status indicator: `✓` = under 150 lines (healthy), `⚠️` = over 150 lines (consider cleanup)

```python
# Cross-platform line counting (works on Windows, macOS, Linux)
from pathlib import Path

def count_lines(filepath):
    try:
        return len(Path(filepath).expanduser().read_text().splitlines())
    except:
        return 0
```

**Display format:**
```
════════════════════════════════════════════════════════════
MEMORY HIERARCHY — TARGET FILES
════════════════════════════════════════════════════════════

CLAUDE.md Files:
  ~/.claude/CLAUDE.md (global)           42 lines  ✓
  ./CLAUDE.md (project)                 156 lines  ⚠️
  ./CLAUDE.local.md (personal)           12 lines  ✓
  ./src/CLAUDE.md (subdirectory)         28 lines  ✓

Rule Files:
  ./.claude/rules/guardrails.md          8 lines  ✓
  ./.claude/rules/coding-style.md       15 lines  ✓  [paths: src/]
  ~/.claude/rules/model-preferences.md  10 lines  ✓

Auto Memory:
  ~/.claude/projects/.../memory/         3 files (general.md, tool-usage.md, workflow.md)

Other:
  AGENTS.md                              ✗ not found

────────────────────────────────────────────────────────────
⚠️  ./CLAUDE.md exceeds 150 lines
    Tip: Run /reflect --dedupe to consolidate similar entries
    Tip: Run /reflect --organize to redistribute entries across tiers
────────────────────────────────────────────────────────────

To create new targets:
  touch AGENTS.md                    # Enable AGENTS.md sync
  touch CLAUDE.local.md              # Personal learnings (gitignored)
  mkdir -p .claude/rules             # Enable modular rule files

════════════════════════════════════════════════════════════
```

**Logic:**
- Show warning section only if ANY file exceeds 150 lines; list all files over threshold
- Always suggest `--dedupe` and `--organize` as remediation
- Show path-scoping info for rule files with `paths:` frontmatter

Exit after showing targets (don't process learnings).
