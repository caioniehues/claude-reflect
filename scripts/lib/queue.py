#!/usr/bin/env python3
"""Durable per-project learnings queue I/O (atomic writes, locking, migration).

Cross-platform compatible (Windows, macOS, Linux).
Part of the reflect_utils split (#8); reflect_utils re-exports these names.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .paths import (
    get_queue_path,
    get_global_queue_path,
    get_migration_sentinel_path,
    iso_timestamp,
    backup_timestamp,
)


def migrate_global_queue() -> None:
    """Migrate items from the legacy global queue to per-project queues.

    Each queue item has a 'project' field with the original cwd.
    Items are distributed to their respective project queues, then
    the global queue is cleared.
    """
    global_path = get_global_queue_path()
    if not global_path.exists():
        return

    try:
        items = json.loads(global_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return

    if not items:
        # Empty global queue — remove file so future calls skip immediately
        global_path.unlink(missing_ok=True)
        return

    # Group items by project
    by_project: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        project = item.get("project", "")
        if project not in by_project:
            by_project[project] = []
        by_project[project].append(item)

    # Write each group to its project queue
    for project, project_items in by_project.items():
        if not project:
            continue
        try:
            project_queue_path = get_queue_path(project)
            # Merge with any existing project queue
            existing = []
            if project_queue_path.exists():
                try:
                    existing = json.loads(
                        project_queue_path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, IOError):
                    existing = []
            existing.extend(project_items)
            _atomic_write_json(project_queue_path, existing)
        except Exception:
            continue

    # Remove global queue after successful migration so future calls skip via exists() check
    global_path.unlink(missing_ok=True)


def run_migrations_once() -> None:
    """Run one-shot legacy migrations, guarded by a sentinel.

    Moved out of load_queue — which fired on every hook and mutated the
    filesystem across every project on each capture — so queue reads stay pure
    and testable. Called once per session from the SessionStart hook.
    """
    sentinel = get_migration_sentinel_path()
    if sentinel.exists():
        return
    try:
        migrate_global_queue()
    except Exception:
        # Don't mark done on failure — a transient error would otherwise strand
        # the legacy global queue forever (the silent-loss mode #1 guards).
        return
    try:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(iso_timestamp(), encoding="utf-8")
    except OSError:
        pass


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON to ``path`` atomically (temp file + os.replace + fsync).

    A crash mid-write leaves the prior file intact — os.replace is atomic, so a
    reader never sees a half-written queue.
    """
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".queue-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _quarantine_queue(path: Path) -> Path | None:
    """Move a corrupt/unusable queue file into a co-located backups dir.

    Backups live at ``path.parent / "backups"`` so per-project queues keep
    per-project backups (and tests never touch the real ~/.claude). Returns the
    backup path, or None on failure.
    """
    if not path.exists():
        return None
    backups = path.parent / "backups"
    try:
        backups.mkdir(parents=True, exist_ok=True)
        dest = backups / f"{path.name}.{backup_timestamp()}.{os.getpid()}.corrupt"
        os.replace(str(path), str(dest))
        return dest
    except OSError:
        return None


class _QueueLock:
    """Best-effort cross-platform advisory lock via an O_EXCL lockfile.

    Durability outranks mutual exclusion: on acquire-timeout we proceed WITHOUT
    the lock rather than dropping the capture or hanging the prompt. A stale
    lock (from a crashed holder, older than STALE_SECONDS) is broken.
    """
    STALE_SECONDS = 15.0

    def __init__(self, target: Path, timeout: float = 5.0, poll: float = 0.05):
        self.lock_path = target.parent / (target.name + ".lock")
        self.timeout = timeout
        self.poll = poll
        self._held = False

    def __enter__(self) -> "_QueueLock":
        import time
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                self._held = True
                return self
            except FileExistsError:
                self._break_if_stale()
                if time.monotonic() >= deadline:
                    return self  # give up the lock, never the capture
                time.sleep(self.poll)
            except OSError:
                return self  # lock dir unwritable — proceed unlocked

    def _break_if_stale(self) -> None:
        import time
        try:
            age = time.time() - self.lock_path.stat().st_mtime
            if age > self.STALE_SECONDS:
                os.unlink(str(self.lock_path))
        except OSError:
            pass

    def __exit__(self, *exc: Any) -> bool:
        if self._held:
            try:
                os.unlink(str(self.lock_path))
            except OSError:
                pass
        return False


def load_queue(project_dir: str | None = None) -> list[dict[str, Any]]:
    """Load the project-scoped learnings queue. Pure read — no migration.

    Corruption-safe: an unparseable or non-list queue file is quarantined to a
    backups dir and an empty queue returned, so a bad file is never silently
    overwritten (which would lose every queued capture).
    """
    path = get_queue_path(project_dir)
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except (IOError, OSError):
        return []
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _quarantine_queue(path)
        return []
    if not isinstance(data, list):
        # Non-list JSON (e.g. {}) — quarantine and coerce to [] rather than
        # raising an AttributeError that would swallow the capture.
        _quarantine_queue(path)
        return []
    return data


def save_queue(items: list[dict[str, Any]], project_dir: str | None = None) -> None:
    """Save learnings queue to the project-scoped file (atomic write)."""
    path = get_queue_path(project_dir)
    _atomic_write_json(path, items)


def append_to_queue(item: dict[str, Any], project_dir: str | None = None) -> None:
    """Append a single item to the project-scoped queue.

    The read-modify-write is guarded by a file lock so two concurrent sessions
    in the same project don't clobber each other's captures.
    """
    path = get_queue_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _QueueLock(path):
        items = load_queue(project_dir)
        items.append(item)
        save_queue(items, project_dir)


def create_queue_item(
    message: str,
    item_type: str,
    patterns: str,
    confidence: float,
    sentiment: str,
    decay_days: int,
    project: str | None = None
) -> dict[str, Any]:
    """Create a properly formatted queue item."""
    return {
        "type": item_type,
        "message": message,
        "timestamp": iso_timestamp(),
        "project": project or os.getcwd(),
        "patterns": patterns,
        "confidence": confidence,
        "sentiment": sentiment,
        "decay_days": decay_days,
    }
