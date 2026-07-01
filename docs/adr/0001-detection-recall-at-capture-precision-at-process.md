---
status: accepted
---

# Detection: recall at capture, precision at process

The two-stage detection pipeline has asymmetric failure costs. Precision applied
at the **capture stage** (`detect_patterns` in the `UserPromptSubmit` hook) drops
messages *permanently* — `capture_learning.py` only queues when `item_type` is
truthy, so any `None` return is an unrecoverable false negative that violates the
product promise ("never lose your corrections"). Precision applied at the
**process stage** (`/reflect`) is human-reviewed and reversible — a false positive
costs one line of review noise. We therefore make the capture-stage regex a pure
cheap **recall** filter and move all **precision** to the process stage, judged
inline by the `/reflect` agent.

## Decision

1. **Capture = recall.** Regex over-captures. Retire the capture-time precision
   tables — `FALSE_POSITIVE_PATTERNS`, `NON_CORRECTION_PHRASES`, and
   `FORWARD_PIVOT_PATTERNS` (the last merged from upstream PR #37). The regex layer
   keeps only wide recall signals (correction openers, `remember:`, positive
   markers) plus the cheap structural guards that prevent obvious non-user content
   from entering the queue (length cap, `should_include_message`).
2. **Process = precision, inline.** Delete the subprocess semantic layer on the
   **learning-validation path** — `validate_queue_items` / `semantic_analyze`
   (invoked via `claude -p`) and `/reflect` Step 1.5. The `/reflect` agent, which
   already reads every queued item to present it for review, judges each item's
   reusability inline. **Scope limit:** this ADR covers only the core capture→queue
   →`/reflect` learning path. The other `semantic_detector.py` consumers —
   `validate_tool_errors` (`--scan-history`) and `detect_contradictions`
   (`--organize`) — are separate flows the grill did not cover; move them to inline
   judgment too when convenient, but that is not decided here.

## Considered options

- **Precision at capture (status quo).** Hand-tuned regex precision tables filter
  at hook time. Rejected: every filtered phrase is a silent permanent drop with no
  review and no second chance — the one place in the system where a precision miss
  is unrecoverable. Directly fights the core promise.
- **Precision at process via subprocess `claude -p` (status quo Step 1.5).**
  A second Claude (sonnet) validates each queued item in its own process. Rejected:
  pays per-item latency and cost (sequential 30s timeouts), uses a weaker model, and
  **silently no-ops when `claude` is unavailable** — unavailability is
  indistinguishable from "not a learning", so every item passes unvalidated
  (was must-fix #5). It is also redundant by construction: a second Claude judging
  what the first `/reflect` Claude is already about to show the user.
- **Precision at process, inline (chosen).** The `/reflect` agent judges directly.
  Faster, uses the smarter main-loop model, cannot silently bypass, and deletes
  ~500 LOC of subprocess plumbing.

## Consequences

- **Retires must-fix #5** (semantic silent-bypass) by construction — there is no
  subprocess left to be unavailable.
- **Noisier queue** is acceptable at observed scale. Measured: live queue 0 items;
  a heavy 2-session project (151 user turns) surfaces ~10 corrections under the
  current regex, single-digit tokens under a wide net. Even with 10× over-capture
  and 10× margin, the queue is low-thousands of tokens against a ~120k smart-zone
  budget — so loading rejects into the `/reflect` agent's context (the only thing
  the subprocess bought) costs nothing here. Revisit if a real queue ever approaches
  the smart zone; batching or a subprocess pre-filter becomes justified then.
- **Deletions:** the learning-validation subprocess path (`validate_queue_items` /
  `semantic_analyze`) and its `/reflect` Step 1.5; the three precision tables and
  their branches in `detect_patterns`. `semantic_detector.py` is emptied only if
  its `--scan-history` / `--organize` consumers also move inline (see scope limit).
  The forward-pivot guard from PR #37 is intentionally reverted — keeping it only
  made sense on the regex-precision path this ADR rejects.
- **Multi-language "for free":** capture-time CJK/language precision stops mattering
  once precision is an LLM judging intent inline, not regex matching keywords.
- Supersedes the "regex vs semantic" open question (REVIEW.md Insight I).
