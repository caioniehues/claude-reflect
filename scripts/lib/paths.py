#!/usr/bin/env python3
"""Path, config, and sentinel utilities for claude-reflect.

Cross-platform compatible (Windows, macOS, Linux).
Part of the reflect_utils split (#8); reflect_utils re-exports these names.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone


def get_queue_path(project_dir: str | None = None) -> Path:
    """Get path to learnings queue file, scoped to the current project.

    Queue files are stored per-project to prevent cross-project leakage:
      ~/.claude/projects/<encoded>/learnings-queue.json

    Falls back to global path if project directory cannot be determined.
    """
    try:
        folder_name = get_project_folder_name(project_dir)
        return get_claude_dir() / "projects" / folder_name / "learnings-queue.json"
    except Exception:
        # Fallback to global path if encoding fails
        return Path.home() / ".claude" / "learnings-queue.json"


def get_global_queue_path() -> Path:
    """Get path to the legacy global learnings queue file.

    Used for migration: items from the old global queue are distributed
    to their per-project queues on first access.
    """
    return Path.home() / ".claude" / "learnings-queue.json"


def get_migration_sentinel_path() -> Path:
    """Sentinel marking legacy migration as done (see run_migrations_once)."""
    return get_claude_dir() / ".reflect-migration-done"


def get_backup_dir() -> Path:
    """Get path to learnings backup directory."""
    return Path.home() / ".claude" / "learnings-backups"


def get_claude_dir() -> Path:
    """Get path to .claude directory."""
    return Path.home() / ".claude"


def get_cleanup_period_days() -> int | None:
    """Get cleanupPeriodDays from ~/.claude/settings.json. Returns None if not set."""
    settings_path = get_claude_dir() / "settings.json"
    if not settings_path.exists():
        return None
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        return settings.get("cleanupPeriodDays")
    except (json.JSONDecodeError, IOError):
        return None


def get_cleanup_warned_sentinel_path() -> Path:
    """Sentinel marking the cleanupPeriodDays retention nag as already shown."""
    return get_claude_dir() / ".reflect-cleanup-warned"


def should_warn_cleanup_once() -> bool:
    """Whether to show the retention nag this session.

    True only when cleanupPeriodDays is unset or too low AND the nag has not been
    shown before. Writes the sentinel on the first True so the warning fires once,
    not every session at the default 30 (hook noise, review insight IV).
    """
    cleanup_days = get_cleanup_period_days()
    if cleanup_days is not None and cleanup_days > 30:
        return False
    sentinel = get_cleanup_warned_sentinel_path()
    if sentinel.exists():
        return False
    try:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(iso_timestamp(), encoding="utf-8")
    except OSError:
        pass
    return True


def get_project_folder_name(project_dir: str | None = None) -> str:
    """Encode a project directory path using Claude Code's folder naming convention.

    /Users/bob/myapp → -Users-bob-myapp
    """
    project_path = Path(project_dir).resolve() if project_dir else Path.cwd().resolve()
    folder_name = str(project_path).replace("/", "-").replace("\\", "-")
    if folder_name.startswith("-"):
        folder_name = folder_name[1:]
    return "-" + folder_name


def iso_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def backup_timestamp() -> str:
    """Get timestamp for backup filenames."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")
