#!/usr/bin/env bash
# install.sh — Claude Usage Widget Installer
# Installs the widget and its dependencies securely using 'uv'.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/claude-widget"
CONFIG_DIR="$HOME/.config/claude-widget"
AUTOSTART_DIR="$HOME/.config/autostart"

# ── Colours ────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   Claude Usage Widget — Installer     ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── 1. System dependencies ─────────────────────────────────────────────────
info "Checking for system dependencies…"
MISSING_PKGS=()
for pkg in python3-gi gir1.2-gtk-3.0; do
    dpkg -l "$pkg" &>/dev/null || MISSING_PKGS+=("$pkg")
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    info "Installing system packages: ${MISSING_PKGS[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y "${MISSING_PKGS[@]}"
fi

# Check for uv
if ! command -v uv &>/dev/null; then
    info "Installing uv (fast Python installer)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "$HOME/.cargo/env"
fi

# ── 2. Create Install Directory & Config ───────────────────────────────────
info "Setting up installation at $INSTALL_DIR…"
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR" && chmod 700 "$CONFIG_DIR"
mkdir -p "$AUTOSTART_DIR"

# ── 3. Sync dependencies with uv ──────────────────────────────────────────
info "Syncing dependencies with uv…"
cp "$SCRIPT_DIR/pyproject.toml" "$INSTALL_DIR/pyproject.toml"
cd "$INSTALL_DIR"
# python3-gi is a system package that cannot be pip-installed; the venv must
# be created with --system-site-packages so GTK bindings are accessible.
if [ ! -d "$INSTALL_DIR/.venv" ]; then
    uv venv --system-site-packages --quiet "$INSTALL_DIR/.venv"
fi
uv sync --quiet

# ── 4. Install widget script ───────────────────────────────────────────────
info "Copying widget script…"
cp "$SCRIPT_DIR/claude_widget.py" "$INSTALL_DIR/claude_widget.py"
chmod +x "$INSTALL_DIR/claude_widget.py"

# ── 5. Create default config (if missing) ──────────────────────────────────
CONFIG_FILE="$CONFIG_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    info "Creating default config at $CONFIG_FILE"
    cat > "$CONFIG_FILE" << 'EOF'
{
  "session_key": "",
  "org_id": "",
  "refresh_interval": 300,
  "position_x": -15,
  "position_y": 50,
  "widget_width": 230,
  "opacity": 0.93,
  "debug": false
}
EOF
    chmod 600 "$CONFIG_FILE"
else
    chmod 600 "$CONFIG_FILE"
fi

# ── 6. Autostart desktop entry ─────────────────────────────────────────────
AUTOSTART_FILE="$AUTOSTART_DIR/claude-widget.desktop"
info "Creating autostart entry at $AUTOSTART_FILE…"
cat > "$AUTOSTART_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Claude Usage Widget
Comment=Displays Claude.ai plan usage as a desktop widget
Exec=$HOME/.local/bin/uv run --project $INSTALL_DIR $INSTALL_DIR/claude_widget.py
Icon=utilities-system-monitor
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-Cinnamon-Autostart-enabled=true
EOF

# ── 7. Create convenience launcher in PATH ─────────────────────────────────
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
LAUNCHER="$BIN_DIR/claude-widget"
info "Creating launcher at $LAUNCHER…"
cat > "$LAUNCHER" << EOF
#!/usr/bin/env bash
exec uv run --project "$INSTALL_DIR" "$INSTALL_DIR/claude_widget.py" "\$@"
EOF
chmod +x "$LAUNCHER"

# ── 8. Run first-time setup wizard ─────────────────────────────────────────
echo ""
SESSION_KEY=$(uv run --project "$INSTALL_DIR" "$INSTALL_DIR/claude_widget.py" -c "
import json, pathlib
cf = pathlib.Path('$CONFIG_FILE')
if cf.exists():
    try:
        d = json.load(cf.open())
        print(d.get('session_key', ''))
    except:
        pass
" 2>/dev/null || true)

if [ -z "$SESSION_KEY" ]; then
    info "Running setup wizard…"
    echo ""
    uv run --project "$INSTALL_DIR" "$INSTALL_DIR/claude_widget.py" --setup
fi

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}✓ Installation complete (using uv)!${NC}"
echo ""
echo "  Commands:"
echo "    claude-widget              — Start the widget"
echo "    claude-widget --dump-api   — Inspect raw API response"
echo "    claude-widget --setup      — Re-run configuration wizard"
echo "    claude-widget --debug      — Verbose logging"
echo ""
echo "  Config:  $CONFIG_DIR/config.json"
echo "  Logs:    $CONFIG_DIR/widget.log"
echo ""
echo "  The widget will auto-start at next login."
echo "  To start now:  claude-widget &"
echo ""
