#!/usr/bin/env python3
"""Compact tool-call sequence extraction — pass-1 for `/reflect-agents`.

Thin subprocess seam over ``extract_tool_sequences`` / ``aggregate_tool_sequences``
(ADR-0003, #15). Reads assistant ``tool_use`` blocks from session JSONL and emits a
token-cheap distillate of recurring tool-call shapes — names, occurrence counts,
and the observed tool set — with the bulky tool inputs stripped. The tool set per
cluster becomes each proposed agent's evidence-scoped `tools` allowlist (Slice 5).

Cross-platform compatible (Windows, macOS, Linux).

Usage:
    python extract_tool_sequences.py <session-file> [session-file...]
    python extract_tool_sequences.py --project <project-dir>
    python extract_tool_sequences.py --all

Options:
    --min-count N   Minimum identical-sequence occurrences to report (default: 2)
    --project DIR   Scan all sessions for a specific project directory
    --all           Scan all sessions across all projects (cross-project sweep)
    --days N        Coarse recency window in days (default: 14). 0 = no limit.

The `--project` / `--all` walks reuse the shared cross-project traversal
(`_iter_project_sessions`) so the `--days` window and per-session project
attribution match `/reflect --all-projects` exactly (ADR-0002 shared machinery).
Output is JSON, consumed by the command layer.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Add this directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.reflect_utils import (
    extract_tool_sequences,
    aggregate_tool_sequences,
    get_project_folder_name,
    _iter_project_sessions,
)


def _walk_sessions(project_dir, all_projects, days):
    """Session files to scan, via the shared cross-project walk.

    For ``--all`` every project folder is swept. For ``--project`` the walk is
    filtered to the folder matching that directory: the **exact** encoded name
    wins, and a basename substring match is only a fallback used when no exact
    folder exists (the underscore-vs-hyphen encoding mismatch). Exact-first is
    load-bearing — an unconditional substring match would pull in sibling folders
    (e.g. ``-repo`` and ``-repo-fork``) and corrupt cross-project reach. Reusing
    ``_iter_project_sessions`` gives the ``--days`` window for free (US20 DRY).
    """
    walk = list(_iter_project_sessions(days=days))
    if all_projects:
        for _folder, files in walk:
            yield from files
        return

    target = get_project_folder_name(project_dir)
    exact = [files for folder, files in walk if folder == target]
    if exact:
        for files in exact:
            yield from files
        return

    # Fallback only when no exact folder matched: basename substring.
    basename = Path(project_dir).name
    for folder, files in walk:
        if basename and basename in folder:
            yield from files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract compact tool-call sequences from session files (pass-1)."
    )
    parser.add_argument("files", nargs="*", help="Session file(s) to scan")
    parser.add_argument("--min-count", type=int, default=2,
                        help="Minimum identical-sequence occurrences (default: 2)")
    parser.add_argument("--project", type=str,
                        help="Scan all sessions for a specific project directory")
    parser.add_argument("--all", action="store_true", dest="all_projects",
                        help="Scan all sessions across all projects")
    parser.add_argument("--days", type=int, default=14,
                        help="Coarse recency window in days (default: 14). 0 = no limit.")
    args = parser.parse_args()

    days = None if args.days == 0 else args.days

    if args.files:
        session_files = [Path(f) for f in args.files]
    elif args.project or args.all_projects:
        session_files = list(_walk_sessions(args.project, args.all_projects, days))
    else:
        parser.print_help()
        return 1

    if not session_files:
        print("No session files found.", file=sys.stderr)
        return 1

    records = []
    for session_file in session_files:
        if not session_file.exists():
            print(f"Warning: session file not found: {session_file}", file=sys.stderr)
            continue
        records.extend(extract_tool_sequences(session_file))

    clusters = aggregate_tool_sequences(records, min_occurrences=args.min_count)

    # JSON is the machine-facing default consumed by the command layer.
    print(json.dumps(clusters, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
