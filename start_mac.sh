#!/usr/bin/env bash
# start_mac.sh — Claude Usage Widget macOS Launcher

# Auto-detect Homebrew site-packages
HB_PYTHON_PATH=$(find /opt/homebrew/lib -name "site-packages" -type d | grep "python3.1" | head -n 1 || echo "")
if [ -z "$HB_PYTHON_PATH" ]; then
    HB_PYTHON_PATH=$(find /usr/local/lib -name "site-packages" -type d | grep "python3.1" | head -n 1 || echo "")
fi

# Set PYTHONPATH to include Homebrew's gi and cairo
export PYTHONPATH="$HB_PYTHON_PATH:${PYTHONPATH:-}"

# Set DYLD_FALLBACK_LIBRARY_PATH so the system can find Homebrew dylibs
# We use FALLBACK to avoid breaking system libraries or triggering SIP protections unnecessarily.
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

exec uv run claude_widget.py "$@"
