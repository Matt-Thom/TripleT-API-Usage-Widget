#!/usr/bin/env bash
# start_mac.sh — Claude Usage Widget macOS Launcher

# Auto-detect Homebrew site-packages
HB_PYTHON_PATH=$(find /opt/homebrew/lib -name "site-packages" -type d | grep "python3.1" | head -n 1 || echo "")
if [ -z "$HB_PYTHON_PATH" ]; then
    HB_PYTHON_PATH=$(find /usr/local/lib -name "site-packages" -type d | grep "python3.1" | head -n 1 || echo "")
fi

# Set PYTHONPATH to include Homebrew's gi and cairo
export PYTHONPATH="$HB_PYTHON_PATH:${PYTHONPATH:-}"

# Set DYLD_LIBRARY_PATH (more aggressive than FALLBACK)
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:${DYLD_LIBRARY_PATH:-}"
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

# Debug info
echo "[DEBUG] PYTHONPATH: $PYTHONPATH"
echo "[DEBUG] DYLD_LIBRARY_PATH: $DYLD_LIBRARY_PATH"

# Try to run via the venv directly if it exists, to avoid 'uv run' environment scrubbing
if [ -f ".venv/bin/python" ]; then
    echo "[DEBUG] Launching via .venv/bin/python..."
    exec .venv/bin/python claude_widget.py "$@"
else
    echo "[DEBUG] Launching via uv run..."
    exec uv run claude_widget.py "$@"
fi
