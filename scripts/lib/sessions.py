#!/usr/bin/env python3
"""Session-JSONL extraction and tool-error aggregation.

Cross-platform compatible (Windows, macOS, Linux).
Part of the reflect_utils split (#8); reflect_utils re-exports these names.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .patterns import _should_include_message, is_correction_candidate


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
