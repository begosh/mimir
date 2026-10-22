#!/usr/bin/env bash
# =============================================================================
# M Í M I R // Agent Skill Installer for Linux / macOS / WSL
# Installs one shared package with CLI directory links
# Supports local repo execution and direct curl pipe:
#   curl -fsSL https://raw.githubusercontent.com/begosh/mimir/main/install.sh | bash -s -- --global
# =============================================================================

set -e

REPO_URL="https://github.com/begosh/mimir.git"
TEMP_DIR=""

cleanup() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"

if [ -f "$SCRIPT_DIR/scripts/install.py" ]; then
    INSTALLER="$SCRIPT_DIR/scripts/install.py"
else
    # Running via pipe (curl | bash)
    echo "[*] Fetching Mímir repository..."
    TEMP_DIR="$(mktemp -d 2>/dev/null || mktemp -d -t 'mimir-install')"
    git clone --depth 1 "$REPO_URL" "$TEMP_DIR" >/dev/null 2>&1
    INSTALLER="$TEMP_DIR/scripts/install.py"
fi

# Locate Python 3
if command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PY_BIN="python"
else
    echo "[!] Error: Python 3 is required to install Mímir but was not found in PATH." >&2
    exit 1
fi

if [ -n "$TEMP_DIR" ]; then
    for arg in "$@"; do
        if [ "$arg" = "--link" ] || [ "$arg" = "-l" ]; then
            echo "[!] --link requires a persistent local checkout." >&2
            exit 1
        fi
    done
fi

"$PY_BIN" "$INSTALLER" "$@"
