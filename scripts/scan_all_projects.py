#!/usr/bin/env python3
"""Cross-project global-harvest sweep — pass-1 for `/reflect --all-projects`.

Thin subprocess seam over ``scan_all_projects`` (ADR-0002, #14). Walks every
``~/.claude/projects/<encoded>/`` folder, extracts correction candidates, dedups
across projects with cross-project frequency, and emits a distilled, token-bounded
shortlist. The `/reflect` agent (pass-2) judges the shortlist inline.

Cross-platform compatible (Windows, macOS, Linux).

Usage:
    python scan_all_projects.py [--days N] [--human]

Options:
    --days N   Coarse recency window in days (default: 90). 0 = no limit.
    --human    Print a human-readable summary instead of the default JSON.
"""
import argparse
import json
import os
import sys

# Add this directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.reflect_utils import scan_all_projects


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-project global-harvest sweep (pass-1)."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Coarse recency window in days (default: 90). 0 disables the limit.",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Human-readable summary instead of the default JSON.",
    )
    args = parser.parse_args()

    days = None if args.days == 0 else args.days
    result = scan_all_projects(days=days)

    if args.human:
        gc = result["global_candidates"]
        ps = result["project_specific"]
        print(f"Scanned {result['projects_scanned']} project(s).\n")
        print(f"=== Global candidates ({len(gc)}) — ranked by cross-project frequency ===")
        for c in gc:
            print(f"  [seen in {c['seen_in_projects']} projects] {c['learning']}")
        print(f"\n=== Project-specific ({len(ps)} project(s)) — not actionable here ===")
        for folder, bucket in sorted(ps.items()):
            print(f"  {folder}: {bucket['count']} correction(s) — run /reflect --scan-history there")
        return 0

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
