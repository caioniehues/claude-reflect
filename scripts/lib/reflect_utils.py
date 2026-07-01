#!/usr/bin/env python3
"""Shared utilities for claude-reflect hooks and scripts.

Cross-platform compatible (Windows, macOS, Linux).

Re-export shim (#8). The implementation was split into focused, single-concern
modules; this module preserves the historical ``from lib.reflect_utils import …``
surface so every caller (commands, hooks, tests) keeps working unchanged:

- ``paths``    — path/config/sentinel utilities and timestamps
- ``patterns`` — correction/positive/guardrail detection
- ``queue``    — durable per-project queue I/O (atomic writes, locking, migration)
- ``memory``   — memory-hierarchy discovery, auto memory, routing suggestions
- ``sessions`` — session-JSONL extraction and tool-error aggregation

Relative imports keep this working whether the package is reached as ``lib`` or
``scripts.lib``.
"""
from __future__ import annotations

from .paths import (
    get_queue_path,
    get_global_queue_path,
    get_migration_sentinel_path,
    get_backup_dir,
    get_claude_dir,
    get_cleanup_period_days,
    get_cleanup_warned_sentinel_path,
    should_warn_cleanup_once,
    get_project_folder_name,
    iso_timestamp,
    backup_timestamp,
)
from .patterns import (
    EXPLICIT_PATTERNS,
    POSITIVE_PATTERNS,
    CORRECTION_PATTERNS,
    GUARDRAIL_PATTERNS,
    CJK_CORRECTION_PATTERNS,
    MAX_CAPTURE_PROMPT_LENGTH,
    MAX_WEAK_PATTERN_LENGTH,
    MIN_SHORT_CORRECTION_LENGTH,
    Detection,
    _NO_DETECTION,
    detect_patterns,
    is_correction_candidate,
    should_include_message,
    _should_include_message,
)
from .queue import (
    migrate_global_queue,
    run_migrations_once,
    _atomic_write_json,
    _quarantine_queue,
    _QueueLock,
    load_queue,
    save_queue,
    append_to_queue,
    create_queue_item,
)
from .memory import (
    EXCLUDED_DIRS,
    _parse_rule_frontmatter,
    find_claude_files,
    suggest_claude_file,
    get_auto_memory_path,
    read_auto_memory,
    _AUTO_MEMORY_TOPICS,
    suggest_auto_memory_topic,
    read_all_memory_entries,
)
from .sessions import (
    extract_user_messages,
    extract_tool_rejections,
    TOOL_ERROR_EXCLUDE_PATTERNS,
    PROJECT_SPECIFIC_ERROR_PATTERNS,
    extract_tool_errors,
    aggregate_tool_errors,
)

__all__ = [
    # paths
    "get_queue_path", "get_global_queue_path", "get_migration_sentinel_path",
    "get_backup_dir", "get_claude_dir", "get_cleanup_period_days",
    "get_cleanup_warned_sentinel_path", "should_warn_cleanup_once",
    "get_project_folder_name", "iso_timestamp", "backup_timestamp",
    # patterns
    "EXPLICIT_PATTERNS", "POSITIVE_PATTERNS", "CORRECTION_PATTERNS",
    "GUARDRAIL_PATTERNS", "CJK_CORRECTION_PATTERNS", "MAX_CAPTURE_PROMPT_LENGTH",
    "MAX_WEAK_PATTERN_LENGTH", "MIN_SHORT_CORRECTION_LENGTH", "Detection",
    "_NO_DETECTION", "detect_patterns", "is_correction_candidate",
    "should_include_message", "_should_include_message",
    # queue
    "migrate_global_queue", "run_migrations_once", "_atomic_write_json",
    "_quarantine_queue", "_QueueLock", "load_queue", "save_queue",
    "append_to_queue", "create_queue_item",
    # memory
    "EXCLUDED_DIRS", "_parse_rule_frontmatter", "find_claude_files",
    "suggest_claude_file", "get_auto_memory_path", "read_auto_memory",
    "_AUTO_MEMORY_TOPICS", "suggest_auto_memory_topic", "read_all_memory_entries",
    # sessions
    "extract_user_messages", "extract_tool_rejections",
    "TOOL_ERROR_EXCLUDE_PATTERNS", "PROJECT_SPECIFIC_ERROR_PATTERNS",
    "extract_tool_errors", "aggregate_tool_errors",
]
