#!/usr/bin/env python3
"""Memory-hierarchy discovery, auto memory, and routing suggestions.

Cross-platform compatible (Windows, macOS, Linux).
Part of the reflect_utils split (#8); reflect_utils re-exports these names.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .paths import get_claude_dir, get_project_folder_name


# Directories to exclude when searching for CLAUDE.md files
EXCLUDED_DIRS = {
    'node_modules', '.git', '.svn', '.hg', 'venv', '.venv', 'env', '.env',
    '__pycache__', '.pytest_cache', '.mypy_cache', 'dist', 'build',
    '.next', '.nuxt', 'coverage', '.coverage', 'htmlcov',
    'vendor', 'target', 'out', 'bin', 'obj',
}


def _parse_rule_frontmatter(filepath: Path) -> dict[str, Any] | None:
    """Parse YAML-like frontmatter from a .claude/rules/*.md file.

    Extracts 'paths:' list without requiring PyYAML. Frontmatter is delimited
    by '---' lines at the start of the file.

    Returns:
        Dict with parsed fields (e.g. {"paths": ["src/", "lib/"]}), or None
        if no frontmatter is found.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (IOError, OSError):
        return None

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    # Find closing ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None

    result: dict[str, Any] = {}
    current_key = None
    current_list: list[str] = []

    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Check for "key: value" or "key:" (start of list)
        if ":" in stripped and not stripped.startswith("-"):
            # Save previous list if any
            if current_key and current_list:
                result[current_key] = current_list
                current_list = []

            key, _, value = stripped.partition(":")
            current_key = key.strip()
            value = value.strip()
            if value:
                result[current_key] = value
                current_key = None
        elif stripped.startswith("- ") and current_key:
            current_list.append(stripped[2:].strip().strip('"').strip("'"))

    # Save final list
    if current_key and current_list:
        result[current_key] = current_list

    return result if result else None


def find_claude_files(root_dir: str | None = None) -> list[dict[str, Any]]:
    """
    Find all memory tier files in the project tree.

    Args:
        root_dir: Root directory to search from (defaults to cwd)

    Returns:
        List of dicts with {path, relative_path, type, ...} for each file found.
        Types: 'global', 'root', 'local', 'subdirectory', 'rule', 'user-rule'.
        Rule files include a 'frontmatter' field with parsed YAML frontmatter.
    """
    root = Path(root_dir) if root_dir else Path.cwd()
    results = []

    # Always include global CLAUDE.md
    global_claude = get_claude_dir() / "CLAUDE.md"
    if global_claude.exists():
        results.append({
            "path": str(global_claude),
            "relative_path": "~/.claude/CLAUDE.md",
            "type": "global",
        })

    # Check root CLAUDE.md
    root_claude = root / "CLAUDE.md"
    if root_claude.exists():
        results.append({
            "path": str(root_claude),
            "relative_path": "./CLAUDE.md",
            "type": "root",
        })

    # Check CLAUDE.local.md (personal, gitignored)
    local_claude = root / "CLAUDE.local.md"
    if local_claude.exists():
        results.append({
            "path": str(local_claude),
            "relative_path": "./CLAUDE.local.md",
            "type": "local",
        })

    # Search for CLAUDE.md in subdirectories
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]

        # Skip root (already handled)
        if Path(dirpath) == root:
            continue

        if "CLAUDE.md" in filenames:
            full_path = Path(dirpath) / "CLAUDE.md"
            rel_path = full_path.relative_to(root)
            # Use as_posix() for consistent forward slashes on all platforms
            results.append({
                "path": str(full_path),
                "relative_path": f"./{rel_path.as_posix()}",
                "type": "subdirectory",
            })

    # Discover project rule files: .claude/rules/*.md
    project_rules_dir = root / ".claude" / "rules"
    if project_rules_dir.is_dir():
        for rule_file in sorted(project_rules_dir.glob("*.md")):
            frontmatter = _parse_rule_frontmatter(rule_file)
            rel_path = rule_file.relative_to(root)
            results.append({
                "path": str(rule_file),
                "relative_path": f"./{rel_path.as_posix()}",
                "type": "rule",
                "frontmatter": frontmatter,
            })

    # Discover user-level rule files: ~/.claude/rules/*.md
    user_rules_dir = get_claude_dir() / "rules"
    if user_rules_dir.is_dir():
        for rule_file in sorted(user_rules_dir.glob("*.md")):
            frontmatter = _parse_rule_frontmatter(rule_file)
            results.append({
                "path": str(rule_file),
                "relative_path": f"~/.claude/rules/{rule_file.name}",
                "type": "user-rule",
                "frontmatter": frontmatter,
            })

    return results


def suggest_claude_file(
    learning: str,
    claude_files: list[dict[str, Any]],
    learning_type: str | None = None,
) -> str | None:
    """
    Suggest which memory file a learning should go to.

    This is a hint for Claude to use when reasoning about placement.
    Returns the relative_path of the suggested file, or None to let Claude decide.

    Args:
        learning: The learning text.
        claude_files: List from find_claude_files().
        learning_type: Optional type hint — 'guardrail', 'auto', 'explicit', etc.
    """
    learning_lower = learning.lower()

    # Guardrails → .claude/rules/guardrails.md
    if learning_type == "guardrail":
        # Check if a guardrails rule file already exists
        for cf in claude_files:
            if cf["type"] == "rule" and "guardrail" in Path(cf["path"]).stem.lower():
                return cf["relative_path"]
        # Suggest creating one
        return "./.claude/rules/guardrails.md"

    # Model indicators → existing model-preferences rule or global CLAUDE.md
    model_indicators = ['gpt-', 'claude-', 'gemini-', 'o3', 'o4']
    if any(ind in learning_lower for ind in model_indicators):
        for cf in claude_files:
            if cf["type"] in ("rule", "user-rule") and "model" in Path(cf["path"]).stem.lower():
                return cf["relative_path"]
        return "~/.claude/CLAUDE.md"

    # Global behavioral (always/never/prefer) → global CLAUDE.md
    global_behavioral = ['always ', 'never ', 'prefer ']
    if any(ind in learning_lower for ind in global_behavioral):
        return "~/.claude/CLAUDE.md"

    # Path-scoped rule match: learning mentions a directory covered by a rule's paths
    for cf in claude_files:
        if cf["type"] == "rule" and cf.get("frontmatter"):
            paths = cf["frontmatter"].get("paths", [])
            if isinstance(paths, list):
                for p in paths:
                    if p.lower().rstrip("/") in learning_lower:
                        return cf["relative_path"]

    # Check if learning mentions a specific subdirectory
    for cf in claude_files:
        if cf["type"] == "subdirectory":
            # Extract directory name from path
            dir_name = Path(cf["relative_path"]).parent.name.lower()
            if dir_name in learning_lower:
                return cf["relative_path"]

    # Default: let Claude decide (return None)
    return None


def get_auto_memory_path(project_dir: str | None = None) -> Path:
    """Get the auto memory directory path for a project.

    Returns ~/.claude/projects/<encoded>/memory/
    """
    folder_name = get_project_folder_name(project_dir)
    return get_claude_dir() / "projects" / folder_name / "memory"


def read_auto_memory(project_dir: str | None = None) -> list[dict[str, Any]]:
    """Read all .md files from the project's auto memory directory.

    Returns list of {file, name, entries} where entries are non-empty lines.
    """
    memory_path = get_auto_memory_path(project_dir)
    results = []

    if not memory_path.is_dir():
        return results

    for md_file in sorted(memory_path.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            entries = [line.strip() for line in text.splitlines() if line.strip()]
            results.append({
                "file": str(md_file),
                "name": md_file.stem,
                "entries": entries,
            })
        except (IOError, OSError):
            continue

    return results


# Topic keywords for auto memory file naming
_AUTO_MEMORY_TOPICS = {
    "model-preferences": ["gpt-", "claude-", "gemini-", "o3", "o4", "model", "llm"],
    "tool-usage": ["mcp", "tool", "plugin", "api", "endpoint"],
    "coding-style": ["indent", "format", "style", "naming", "convention", "lint"],
    "environment": ["venv", "env", "docker", "port", "database", "redis", "postgres"],
    "workflow": ["commit", "deploy", "test", "build", "ci", "cd", "pipeline"],
    "debugging": ["debug", "error", "log", "trace", "breakpoint"],
}


def suggest_auto_memory_topic(learning: str) -> str:
    """Suggest a topic filename for an auto memory entry based on keywords.

    Returns a filename stem like 'model-preferences' or 'general'.
    """
    learning_lower = learning.lower()
    best_topic = "general"
    best_score = 0

    for topic, keywords in _AUTO_MEMORY_TOPICS.items():
        score = sum(1 for kw in keywords if kw in learning_lower)
        if score > best_score:
            best_score = score
            best_topic = topic

    return best_topic


def read_all_memory_entries(
    root_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Read bullet-point entries from ALL memory tiers for cross-tier deduplication.

    Scans: CLAUDE.md files, rule files, CLAUDE.local.md, and auto memory.

    Returns list of {text, source_file, source_type, line_number}.
    """
    claude_files = find_claude_files(root_dir)
    entries: list[dict[str, Any]] = []

    # Read entries from each CLAUDE.md / rule / local file
    for cf in claude_files:
        filepath = Path(cf["path"])
        if cf["type"] == "global":
            filepath = Path(cf["path"])
        try:
            text = filepath.read_text(encoding="utf-8")
        except (IOError, OSError):
            continue

        for line_num, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("- "):
                entries.append({
                    "text": stripped[2:].strip(),
                    "source_file": cf["relative_path"],
                    "source_type": cf["type"],
                    "line_number": line_num,
                })

    # Read auto memory entries
    auto_memory = read_auto_memory(root_dir)
    for mem in auto_memory:
        for idx, entry_text in enumerate(mem["entries"]):
            clean = entry_text.lstrip("- ").strip()
            if clean and not clean.startswith("#"):
                entries.append({
                    "text": clean,
                    "source_file": f"~/.claude/projects/.../memory/{mem['name']}.md",
                    "source_type": "auto-memory",
                    "line_number": idx + 1,
                })

    return entries
