#!/usr/bin/env bash
# dev.sh — start a Claude Code session with this repo loaded as a live plugin.
#
# Unlike `/plugin install`, which copies the plugin into ~/.claude/plugins/cache
# (a frozen snapshot), `--plugin-dir` loads the plugin directly from THIS repo.
# Edit any script/command/hook here, run `/reload-plugins` inside the session,
# and the change takes effect immediately — no reinstall.
#
# Usage:
#   ./scripts/dev.sh              # start a dev session in this repo
#   ./scripts/dev.sh --help       # forwarded to claude
#
# Any extra args are forwarded to `claude`.
set -euo pipefail

# Resolve repo root (parent of this script's dir), independent of CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v claude >/dev/null 2>&1; then
  echo "error: 'claude' CLI not found on PATH. Install Claude Code first." >&2
  exit 1
fi

echo "Loading claude-reflect as a live plugin from: ${REPO_ROOT}"
echo "Inside the session, run /reload-plugins after edits to pick up changes."
exec claude --plugin-dir "${REPO_ROOT}" "$@"
