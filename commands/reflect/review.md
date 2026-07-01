# /reflect --review

Disclosed reference for `/reflect`. Read only when the user passes `--review`.
Show queued learnings with their confidence and decay status, then exit without
processing.

```bash
cat ~/.claude/learnings-queue.json | jq -r '.[] | "\(.timestamp) | conf:\(.confidence // 0.5) | decay:\(.decay_days // 90)d | \(.message | .[0:60])"'
```

Display table of learnings with decay status:
```
═══════════════════════════════════════════════════════════
LEARNINGS REVIEW — Confidence & Decay Status
═══════════════════════════════════════════════════════════

┌────┬──────────┬────────┬────────────────────────────────┐
│ #  │ Conf.    │ Decay  │ Learning                       │
├────┼──────────┼────────┼────────────────────────────────┤
│ 1  │ 0.90 ✓   │ 120d   │ Use gpt-5.1 for reasoning     │
│ 2  │ 0.60     │ 60d ⚠  │ Enable flag X for API calls   │
│ 3  │ 0.40 ⚠   │ 30d ⚠  │ Consider using batch mode     │
└────┴──────────┴────────┴────────────────────────────────┘

Legend: ✓ High confidence  ⚠ Low confidence/Near decay
═══════════════════════════════════════════════════════════
```

Exit after showing review (don't process learnings).
