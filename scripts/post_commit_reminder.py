#!/usr/bin/env python3
"""Remind about /reflect after git commits. PostToolUse hook for Bash.

Cross-platform compatible (Windows, macOS, Linux).
This script is called by Claude Code's PostToolUse hook after Bash commands.
It detects git commits and reminds the user to run /reflect.
"""
import sys
import os
import json
import shlex
from typing import Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.reflect_utils import load_queue


def detect_git_commit(command: str) -> Tuple[bool, bool]:
    """Classify a Bash command as a git-commit invocation.

    Tokenizes with shlex and requires *adjacent* ``git`` + ``commit`` argv
    tokens, so substrings inside quotes (echo/grep "git commit"), subcommands
    (``git commit-graph``), and ``--amend`` mentioned inside a commit *message*
    don't false-trigger.

    Returns (is_commit, is_amend). ``is_amend`` is true only when ``--amend``
    appears as a standalone argv token.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Unbalanced quotes etc. — can't reliably parse; treat as non-commit.
        return (False, False)

    is_commit = any(
        tokens[i] == "git" and tokens[i + 1] == "commit"
        for i in range(len(tokens) - 1)
    )
    is_amend = "--amend" in tokens
    return (is_commit, is_amend)


def main() -> int:
    """Main entry point."""
    # Read hook input from stdin
    input_data = sys.stdin.read()
    if not input_data:
        return 0

    try:
        data = json.loads(input_data)
        command = data.get("tool_input", {}).get("command", "")
    except json.JSONDecodeError:
        return 0

    if not command:
        return 0

    # Fire only on a real `git commit` (adjacent argv tokens), and skip amends.
    is_commit, is_amend = detect_git_commit(command)
    if not is_commit or is_amend:
        return 0

    # Build reminder message
    msg = "Git commit detected!"

    items = load_queue()
    if items:
        msg += f" You have {len(items)} queued learning(s)."

    msg += " Feature complete? Run /reflect to process learnings."

    # Output proper JSON for hook response
    response = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg
        }
    }
    print(json.dumps(response))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Never block on errors - just log and exit 0
        print(f"Warning: post_commit_reminder.py error: {e}", file=sys.stderr)
        sys.exit(0)
