#!/usr/bin/env bash
# install_mac.sh — Claude Usage Widget macOS Installer
# Installs dependencies via Homebrew and sets up the environment.

set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   Claude Usage Widget — Mac Installer ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── 1. Check for Homebrew ──────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    error "Homebrew not found. Please install it from https://brew.sh/"
fi

# ── 2. System dependencies ─────────────────────────────────────────────────
info "Installing system dependencies via Homebrew..."
brew install gtk+3 pygobject3 adwaita-icon-theme

# ── 3. Check for uv ────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    info "Installing uv (fast Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# ── 4. Setup virtual environment ───────────────────────────────────────────
info "Syncing Python dependencies..."
uv sync --quiet

# ── 5. Verify environment ──────────────────────────────────────────────────
HB_PYTHON_PATH=$(find /opt/homebrew/lib -name "site-packages" -type d | grep "python3.1" | head -n 1 || echo "")
if [ -z "$HB_PYTHON_PATH" ]; then
    HB_PYTHON_PATH=$(find /usr/local/lib -name "site-packages" -type d | grep "python3.1" | head -n 1 || echo "")
fi

if [ -n "$HB_PYTHON_PATH" ]; then
    info "Found Homebrew Python site-packages at: $HB_PYTHON_PATH"
    if ! PYTHONPATH="$HB_PYTHON_PATH" uv run python3 -c "import gi; import cairo" 2>/dev/null; then
        warn "Environment verification failed. GUI mode might not work correctly."
    else
        info "Environment verification successful!"
    fi
else
    warn "Could not automatically locate Homebrew Python site-packages."
fi

# ── 6. Create macOS Launcher ───────────────────────────────────────────────
LAUNCHER="start_mac.sh"
info "Creating macOS launcher at ./$LAUNCHER..."
cat > "$LAUNCHER" << EOF
#!/usr/bin/env bash
# start_mac.sh — Claude Usage Widget macOS Launcher

# Auto-detect Homebrew site-packages
HB_PYTHON_PATH=\$(find /opt/homebrew/lib -name "site-packages" -type d | grep "python3.1" | head -n 1 || echo "")
if [ -z "\$HB_PYTHON_PATH" ]; then
    HB_PYTHON_PATH=\$(find /usr/local/lib -name "site-packages" -type d | grep "python3.1" | head -n 1 || echo "")
fi

export PYTHONPATH="\$HB_PYTHON_PATH:\${PYTHONPATH:-}"
exec uv run claude_widget.py "\$@"
EOF
chmod +x "$LAUNCHER"

echo ""
echo -e "  ${GREEN}✓ Installation complete!${NC}"
echo ""
echo "  To start the widget on macOS:"
echo "    ./$LAUNCHER"
echo ""
echo "  To run the TUI dashboard:"
echo "    ./$LAUNCHER --tui"
echo ""
