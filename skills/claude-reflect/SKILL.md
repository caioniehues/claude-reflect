---
name: claude-reflect
description: Reminds the user to run /reflect so queued corrections get written into their CLAUDE.md memory. Use when the user finishes a work unit, corrects you in a way worth persisting, says "remember this", or when context is about to compact with learnings pending. Capturing corrections is the hook's job, not yours — this skill is only the nudge to process them.
---

# Claude Reflect — reminder to process learnings

Capture is automatic: a `UserPromptSubmit` hook detects corrections and queues
them to `~/.claude/learnings-queue.json`. You do not capture anything.

Your one job here is the **nudge**: notice when the queue is worth processing and
remind the user to run `/reflect`. The `/reflect` command owns the rest (review,
routing, memory tiers) — point to it, don't restate it.

## When to remind

- The user completes a feature or meaningful work unit.
- The user corrects you in a way that should persist across sessions.
- The user says "remember this" or similar.
- Context is about to compact and the queue has items.

Keep it one line, and let the user decide — surface the nudge, don't nag.
