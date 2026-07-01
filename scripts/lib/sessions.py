#!/usr/bin/env python3
"""Session-JSONL extraction and tool-error aggregation.

Cross-platform compatible (Windows, macOS, Linux).
Part of the reflect_utils split (#8); reflect_utils re-exports these names.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from .patterns import _should_include_message, is_correction_candidate
from .paths import get_claude_dir


def extract_user_messages(session_file: Path, corrections_only: bool = False) -> list[str]:
    """
    Extract user messages from a Claude Code session file (JSONL format).

    Args:
        session_file: Path to the session JSONL file
        corrections_only: If True, only return messages matching correction patterns

    Returns:
        List of user message texts
    """
    if not session_file.exists():
        return []

    messages = []

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Filter: type=user, not isMeta
                if entry.get("type") != "user":
                    continue
                if entry.get("isMeta"):
                    continue

                # Extract text from content (can be string or list)
                content = entry.get("message", {}).get("content", [])

                # Handle string content directly
                if isinstance(content, str):
                    if content and _should_include_message(content):
                        messages.append(content)
                # Handle list of content items
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            if text:
                                # Apply filters (same as bash script)
                                if _should_include_message(text):
                                    messages.append(text)
    except IOError:
        return []

    if corrections_only:
        messages = [m for m in messages if is_correction_candidate(m)]

    return messages


def extract_tool_rejections(session_file: Path) -> list[str]:
    """
    Extract user corrections from tool rejections in session files.

    Matches the behavior of the legacy bash script which looks for:
    - type == "user" entries
    - message.content[] array with type == "tool_result"
    - is_error == true
    - content containing "The user doesn't want to proceed"

    Args:
        session_file: Path to the session JSONL file

    Returns:
        List of user correction texts from tool rejections
    """
    if not session_file.exists():
        return []

    rejections = []

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Must be a user entry (matches bash: select(.type=="user"))
                if entry.get("type") != "user":
                    continue

                # Get message.content array (matches bash: select(.message.content | type == "array"))
                content = entry.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue

                # Look for tool_result items in content array
                for item in content:
                    if not isinstance(item, dict):
                        continue

                    # Must be type == "tool_result" (matches bash: select(.type=="tool_result"))
                    if item.get("type") != "tool_result":
                        continue

                    # Must have is_error == true (matches bash: select(.is_error==true))
                    if not item.get("is_error"):
                        continue

                    # Get the content string
                    tool_content = item.get("content", "")
                    if not isinstance(tool_content, str):
                        continue

                    # Must contain rejection message (matches bash: select(.content | contains(...)))
                    if "The user doesn't want to proceed" not in tool_content:
                        continue

                    # Extract text after "the user said:" (matches bash: awk '/the user said:/{getline; print}')
                    # Note: bash uses lowercase "the user said:", let's be case-insensitive
                    lower_content = tool_content.lower()
                    if "the user said:" in lower_content:
                        # Find the position case-insensitively
                        idx = lower_content.find("the user said:")
                        after_marker = tool_content[idx + len("the user said:"):]
                        # Get the next line (bash uses getline)
                        lines = after_marker.strip().split("\n")
                        if lines and lines[0].strip():
                            rejections.append(lines[0].strip())

    except IOError:
        return []

    return rejections


# EXCLUDE: Claude Code guardrails AND global Claude behavior (not project-specific)
TOOL_ERROR_EXCLUDE_PATTERNS = [
    # Claude Code guardrails - system enforcing its rules
    r"File has not been read yet",
    r"exceeds maximum allowed tokens",
    r"InputValidationError",
    r"not valid JSON",
    r"The user doesn't want to proceed",  # User rejections handled separately
    # Global Claude behavior issues - not project-specific
    r"unexpected EOF while looking for matching",  # Bash quoting
    r"EISDIR|illegal operation on a directory",    # File vs dir confusion
    r"syntax error.*eval",                          # Bash syntax errors
]


# PROJECT-SPECIFIC error patterns that reveal env/config/structure issues
# Format: (error_type, regex_pattern, suggested_guideline_template)
PROJECT_SPECIFIC_ERROR_PATTERNS = [
    # Connection/service errors - often reveal env/config issues
    ("connection_refused",
     r"Connection refused|ECONNREFUSED|connect ECONNREFUSED",
     "Check .env for service URLs - don't assume localhost"),
    ("env_undefined",
     r"(\w+_URL|DATABASE_URL|API_KEY|SECRET).*undefined|not set|is not defined",
     "Load .env file before accessing environment variables"),
    # Database-specific errors
    ("supabase_error",
     r"supabase|Supabase|SUPABASE",
     "Check SUPABASE_URL and SUPABASE_KEY in .env"),
    ("postgres_error",
     r"postgres|PostgreSQL|PGHOST|:5432|password authentication failed",
     "Check DATABASE_URL in .env for PostgreSQL connection"),
    ("redis_error",
     r"redis|REDIS|:6379",
     "Check REDIS_URL in .env for Redis connection"),
    # Path/module errors - reveal project structure
    ("module_not_found",
     r"ModuleNotFoundError|Cannot find module|No module named",
     "Check import paths - verify project structure"),
    ("venv_not_found",
     r"venv.*No such file|activate: No such file|\.venv.*not found",
     "Check virtual environment location"),
    # Port/service conflicts
    ("port_in_use",
     r"address already in use|EADDRINUSE|port.*already.*use",
     "Check if service is already running on this port"),
]


def extract_tool_errors(
    session_file: Path,
    project_specific_only: bool = True
) -> list[dict[str, Any]]:
    """
    Extract tool execution errors from session files.

    Unlike extract_tool_rejections(), this captures TECHNICAL errors where:
    - is_error == true
    - NOT a user rejection (no "doesn't want to proceed")
    - Optionally filtered for project-specific patterns only

    Args:
        session_file: Path to the session JSONL file
        project_specific_only: If True, only return errors matching project-specific patterns

    Returns:
        List of dicts with {error_type, content, project, timestamp, suggested_guideline}
    """
    if not session_file.exists():
        return []

    errors = []

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Must be a user entry (tool results come back as user messages)
                if entry.get("type") != "user":
                    continue

                # Get message.content array
                content = entry.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue

                # Look for tool_result items with is_error
                for item in content:
                    if not isinstance(item, dict):
                        continue

                    if item.get("type") != "tool_result":
                        continue

                    if not item.get("is_error"):
                        continue

                    tool_content = item.get("content", "")
                    if not isinstance(tool_content, str):
                        continue

                    # Skip if matches exclude patterns
                    should_exclude = False
                    for exclude_pattern in TOOL_ERROR_EXCLUDE_PATTERNS:
                        if re.search(exclude_pattern, tool_content, re.IGNORECASE):
                            should_exclude = True
                            break

                    if should_exclude:
                        continue

                    # If project_specific_only, check for matching patterns
                    error_type = "unknown"
                    suggested_guideline = None

                    for etype, pattern, guideline in PROJECT_SPECIFIC_ERROR_PATTERNS:
                        if re.search(pattern, tool_content, re.IGNORECASE):
                            error_type = etype
                            suggested_guideline = guideline
                            break

                    # Skip unknown errors if project_specific_only
                    if project_specific_only and error_type == "unknown":
                        continue

                    errors.append({
                        "error_type": error_type,
                        "content": tool_content[:500],  # Truncate long errors
                        "project": str(session_file.parent.name),
                        "timestamp": entry.get("timestamp", ""),
                        "suggested_guideline": suggested_guideline,
                    })

    except IOError:
        return []

    return errors


def aggregate_tool_errors(
    errors: list[dict[str, Any]],
    min_occurrences: int = 2
) -> list[dict[str, Any]]:
    """
    Group errors by type and return those with multiple occurrences.

    Only repeated errors are valuable for CLAUDE.md - one-off errors are noise.

    Args:
        errors: List of error dicts from extract_tool_errors()
        min_occurrences: Minimum times an error type must occur

    Returns:
        List of aggregated errors with {error_type, count, suggested_guideline,
        confidence, sample_errors}
    """
    from collections import Counter

    # Count by error type
    type_counts = Counter(e["error_type"] for e in errors)

    # Group errors by type
    errors_by_type: dict[str, list[dict[str, Any]]] = {}
    for error in errors:
        etype = error["error_type"]
        if etype not in errors_by_type:
            errors_by_type[etype] = []
        errors_by_type[etype].append(error)

    # Build aggregated results for types meeting threshold
    aggregated = []
    for error_type, count in type_counts.items():
        if count < min_occurrences:
            continue

        samples = errors_by_type[error_type][:3]  # Keep up to 3 samples
        suggested_guideline = samples[0].get("suggested_guideline") if samples else None

        # Higher confidence for more occurrences
        if count >= 5:
            confidence = 0.90
        elif count >= 3:
            confidence = 0.85
        else:
            confidence = 0.70

        aggregated.append({
            "error_type": error_type,
            "count": count,
            "suggested_guideline": suggested_guideline,
            "confidence": confidence,
            "decay_days": 180,  # Tool error learnings decay slower
            "sample_errors": [s["content"][:200] for s in samples],
        })

    # Sort by count descending
    aggregated.sort(key=lambda x: x["count"], reverse=True)

    return aggregated


# ---------------------------------------------------------------------------
# Cross-project sweep — shared pass-1 machinery (ADR-0002 / ADR-0003, #14)
#
# Built once as sessions-layer machinery and reused by both features (US20):
# `scan_all_projects` (learnings, #16) and `/reflect-agents` (roles, #17). The
# walk (`_iter_project_sessions`) is factored out so the tool-sequence sweep can
# share the exact same traversal without duplicating logic.
# ---------------------------------------------------------------------------

# Seconds per day, for the coarse `--days` mtime pre-filter.
_SECONDS_PER_DAY = 86400


def _iter_project_sessions(
    projects_dir: Path | str | None = None,
    days: int | None = 90,
) -> Iterator[tuple[str, list[Path]]]:
    """Yield ``(project_folder_name, [session_files])`` for every project folder.

    The shared cross-project walk over ``~/.claude/projects/<encoded>/`` (ADR-0002
    shared machinery). Globs ``*.jsonl`` so ``agent-*.jsonl`` files are included
    (scan-history requires it). Applies a ``--days`` mtime pre-filter as a coarse
    bound (default 90; ``None`` disables it). Folders whose sessions all fall
    outside the window yield nothing.

    Args:
        projects_dir: Root to walk. Defaults to ``~/.claude/projects``.
        days: Only include session files modified within this many days. ``None``
            includes all.

    Yields:
        Tuples of the encoded project folder name and its in-window session files.
    """
    if projects_dir is None:
        projects_dir = get_claude_dir() / "projects"
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return

    cutoff = None if days is None else time.time() - days * _SECONDS_PER_DAY

    for child in sorted(projects_dir.iterdir()):
        if not child.is_dir():
            continue
        files: list[Path] = []
        for session_file in sorted(child.glob("*.jsonl")):
            if cutoff is not None:
                try:
                    if session_file.stat().st_mtime < cutoff:
                        continue
                except OSError:
                    continue
            files.append(session_file)
        if files:
            yield child.name, files


def _normalize_correction(text: str) -> str:
    """Normalization key for cross-project dedup.

    Lowercase, strip punctuation, collapse whitespace. Exact-normalized grouping
    only — semantic-adjacent grouping is deferred to the pass-2 agent (ADR-0002),
    which judges the distilled shortlist inline. This groups trivially-varied
    restatements ("Use pnpm not npm" / "use pnpm, not npm.") without an LLM.
    """
    key = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", key).strip()


def scan_all_projects(
    projects_dir: Path | str | None = None,
    days: int | None = 90,
    samples_per_project: int = 3,
) -> dict[str, Any]:
    """Pass-1 cross-project sweep for the global harvest (ADR-0002, #14/#16).

    Walks every ``~/.claude/projects/<encoded>/`` folder, extracts correction
    candidates per project via the existing recall predicate
    (``extract_user_messages(..., corrections_only=True)`` → ``is_correction_candidate``),
    dedups across projects on the normalized key, and partitions by **cross-project
    frequency**:

    - seen in **≥2 projects** → ``global_candidates`` (frequency-ranked shortlist;
      the strongest proxy for global-worthiness, biases the pass-2 judge toward
      ``global``).
    - seen in **exactly 1 project** → ``project_specific`` (grouped per project
      with a ``count`` and up to ``samples_per_project`` samples — surface, don't
      suppress, but token-bounded per US7/US8: a count, not an enumeration).

    Returns a distilled, token-bounded shortlist; raw sessions are never returned,
    so cost scales with distinct candidates, not total history.

    Args:
        projects_dir: Root to walk. Defaults to ``~/.claude/projects``.
        days: Coarse recency pre-filter in days (default 90; ``None`` = all).
        samples_per_project: Cap on sample texts kept per project-specific bucket.

    Returns:
        ``{"global_candidates": [...], "project_specific": {...}, "projects_scanned": int}``.
    """
    # normalized_key -> {"projects": {folder: occurrences}, "sample": raw_text}
    groups: dict[str, dict[str, Any]] = {}
    projects_scanned = 0

    for folder, files in _iter_project_sessions(projects_dir, days):
        projects_scanned += 1
        for session_file in files:
            for message in extract_user_messages(session_file, corrections_only=True):
                key = _normalize_correction(message)
                if not key:
                    continue
                group = groups.setdefault(key, {"projects": {}, "sample": message})
                group["projects"][folder] = group["projects"].get(folder, 0) + 1

    global_candidates: list[dict[str, Any]] = []
    project_specific: dict[str, dict[str, Any]] = {}

    for key, group in groups.items():
        project_counts: dict[str, int] = group["projects"]
        n_projects = len(project_counts)
        total_occurrences = sum(project_counts.values())

        if n_projects >= 2:
            global_candidates.append({
                "learning": group["sample"],
                "normalized": key,
                "seen_in_projects": n_projects,
                "projects": sorted(project_counts.keys()),
                "occurrences": total_occurrences,
            })
        else:
            (folder,) = project_counts.keys()
            bucket = project_specific.setdefault(folder, {"count": 0, "samples": []})
            bucket["count"] += 1
            if len(bucket["samples"]) < samples_per_project:
                bucket["samples"].append(group["sample"])

    # Rank by cross-project frequency, then total occurrences (US5).
    global_candidates.sort(
        key=lambda c: (c["seen_in_projects"], c["occurrences"]),
        reverse=True,
    )

    return {
        "global_candidates": global_candidates,
        "project_specific": project_specific,
        "projects_scanned": projects_scanned,
    }


# ---------------------------------------------------------------------------
# Tool-call sequence extraction — pass-1 for /reflect-agents (ADR-0003, #15)
# ---------------------------------------------------------------------------


def _is_tool_result_turn(entry: dict[str, Any]) -> bool:
    """Whether a ``user`` entry is actually a tool_result carrier, not a real turn.

    Tool results come back as ``user`` messages; they must NOT split a task, since
    the assistant's tool loop for one user request is interleaved with them.
    """
    content = entry.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return False
    return any(
        isinstance(item, dict) and item.get("type") == "tool_result"
        for item in content
    )


def extract_tool_sequences(session_file: Path) -> list[dict[str, Any]]:
    """Pass-1 for /reflect-agents: compact tool-name sequences per task (ADR-0003 §5).

    Parses assistant ``tool_use`` blocks into an ordered **tool-name sequence** per
    task, where a *task* is the assistant work following one real user turn (until
    the next real user turn). **Strips the bulky tool inputs** — only names,
    sequences, and the observed tool *set* survive, so the distillate stays small
    over large histories. The per-task ``tools`` set is each role's evidence-scoped
    ``tools`` allowlist in Slice 5.

    Args:
        session_file: Path to a session JSONL file.

    Returns:
        Per-task records: ``{"sequence": [names...], "tools": [sorted set], "project": folder}``.
        Tasks with no tool calls are omitted.
    """
    if not session_file.exists():
        return []

    folder = session_file.parent.name
    tasks: list[list[str]] = []
    current: list[str] = []

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = entry.get("type")
                if etype == "user" and not entry.get("isMeta"):
                    # A real user turn ends the previous task; tool_result carriers do not.
                    if not _is_tool_result_turn(entry):
                        if current:
                            tasks.append(current)
                        current = []
                elif etype == "assistant":
                    content = entry.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "tool_use":
                                name = item.get("name")
                                if name:
                                    current.append(name)
    except IOError:
        return []

    if current:
        tasks.append(current)

    return [
        {"sequence": seq, "tools": sorted(set(seq)), "project": folder}
        for seq in tasks
    ]


def aggregate_tool_sequences(
    records: list[dict[str, Any]],
    min_occurrences: int = 2,
) -> list[dict[str, Any]]:
    """Cluster identical tool-name sequences across records (exact-match, mechanical).

    Exact-match clustering only; semantic role clustering ("these shapes are the
    same locator role") is the pass-2 agent's job (ADR-0003). Emits occurrence
    counts and the union tool-set per cluster — the observed footprint that becomes
    the evidence-scoped ``tools`` allowlist — plus the **cross-project reach** of
    each cluster (``projects`` / ``seen_in_projects``), the signal that routes a
    role to a project-local vs global agent file (Slice 4/5, US18). Records without
    a ``project`` field contribute nothing to reach (reach stays 0).

    Args:
        records: Per-task records from ``extract_tool_sequences``.
        min_occurrences: Minimum identical-sequence count to surface a cluster.

    Returns:
        Clusters ``{"sequence": [...], "count": N, "tools": [...], "projects": [...],
        "seen_in_projects": M}`` sorted by count desc.
    """
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(tuple(record["sequence"]), []).append(record)

    clusters: list[dict[str, Any]] = []
    for seq, group in groups.items():
        count = len(group)
        if count < min_occurrences:
            continue
        projects = sorted({r["project"] for r in group if r.get("project")})
        clusters.append({
            "sequence": list(seq),
            "count": count,
            "tools": sorted(set(seq)),
            "projects": projects,
            "seen_in_projects": len(projects),
        })

    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters
