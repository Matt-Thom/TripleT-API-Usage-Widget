#!/usr/bin/env bash
# start_local.sh — Claude Usage Widget Local Launcher
# Uses 'uv' for fast environment management and dependency installation.

set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC}  $*"; }

# ── 1. Check for system-level python3-gi ──────────────────────────────────
if ! dpkg -l python3-gi &>/dev/null; then
    echo "ERROR: Missing system dependency 'python3-gi'."
    echo "Run: sudo apt install python3-gi gir1.2-gtk-3.0"
    exit 1
fi

# ── 2. Sync dependencies with uv ──────────────────────────────────────────
info "Syncing dependencies with uv..."
# Note: we use --system-site-packages during venv creation (if missing) 
# and uv run will use that venv.
if [ ! -d ".venv" ]; then
    uv venv --system-site-packages --quiet
fi
uv sync --quiet

# ── 3. Check for config ────────────────────────────────────────────────────
CONFIG_FILE="$HOME/.config/claude-widget/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    info "No configuration found. Launching setup wizard..."
    uv run claude_widget.py --setup
fi

# ── 4. Run the widget ──────────────────────────────────────────────────────
info "Starting Claude Usage Widget..."
exec uv run claude_widget.py "$@"
