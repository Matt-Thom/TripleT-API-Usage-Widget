#!/usr/bin/env bash
# install.sh — Claude Usage Widget Installer
# Installs the widget and its dependencies securely using 'uv'.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/claude-widget"
CONFIG_DIR="$HOME/.config/claude-widget"
AUTOSTART_DIR="$HOME/.config/autostart"
VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"

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
echo "  ║   Claude Usage Widget — Installer     ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── 1. System dependencies ─────────────────────────────────────────────────
info "Checking for system dependencies…"

# dpkg -s is the reliable way to check if a package is fully installed
pkg_installed() { dpkg -s "$1" &>/dev/null && dpkg -s "$1" | grep -q "^Status: install ok installed"; }

MISSING_PKGS=()
for pkg in python3-gi python3-gi-cairo gir1.2-gtk-3.0; do
    pkg_installed "$pkg" || MISSING_PKGS+=("$pkg")
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    info "Installing system packages: ${MISSING_PKGS[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y "${MISSING_PKGS[@]}"
fi

# Confirm gi is importable from the system Python before we build the venv
if ! python3 -c "import gi" 2>/dev/null; then
    error "'python3-gi' was installed but 'import gi' still fails.\n       Try: sudo apt-get install --reinstall python3-gi"
fi

# ── Check / install uv ─────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    info "Installing uv (fast Python package manager)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # uv installs to ~/.local/bin; make sure it's on PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
fi

command -v uv &>/dev/null || error "uv not found after installation. Add ~/.local/bin to your PATH and re-run."

# ── 2. Create directories ──────────────────────────────────────────────────
info "Setting up installation at $INSTALL_DIR…"
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR" && chmod 700 "$CONFIG_DIR"
mkdir -p "$AUTOSTART_DIR"

# ── 3. Create / validate the virtual environment ───────────────────────────
# python3-gi is a system package installed for the distro's Python interpreter.
# uv defaults to downloading its own Python, which won't see system site-packages
# even with --system-site-packages. We must pin the venv to the same Python
# executable that we already verified can import gi.
SYSTEM_PYTHON="$(python3 -c 'import sys; print(sys.executable)')"
info "Using system Python: $SYSTEM_PYTHON"

# If an existing venv was built against a different Python or without
# system-site-packages, remove it so we can recreate it correctly.
info "Preparing virtual environment…"
if [ -d "$INSTALL_DIR/.venv" ]; then
    PYVENV_CFG="$INSTALL_DIR/.venv/pyvenv.cfg"
    VENV_PYTHON_PATH=$(grep -i "^home\s*=" "$PYVENV_CFG" 2>/dev/null | cut -d= -f2 | tr -d ' ')
    SYSTEM_PYTHON_DIR="$(dirname "$SYSTEM_PYTHON")"
    if ! grep -qi "include-system-site-packages = true" "$PYVENV_CFG" 2>/dev/null || \
       [ "$VENV_PYTHON_PATH" != "$SYSTEM_PYTHON_DIR" ]; then
        warn "Existing venv is stale (wrong Python or missing system-site-packages) — rebuilding…"
        rm -rf "$INSTALL_DIR/.venv"
    fi
fi

if [ ! -d "$INSTALL_DIR/.venv" ]; then
    uv venv --python "$SYSTEM_PYTHON" --system-site-packages --quiet "$INSTALL_DIR/.venv"
fi

# ── 4. Install pip dependencies directly into the venv ────────────────────
# We use 'uv pip install --python' rather than 'uv sync' because 'uv sync'
# recreates the venv from scratch (losing --system-site-packages) whenever it
# manages the project environment.  'uv pip install' installs straight into the
# existing venv without touching its configuration.
info "Installing Python dependencies…"
# Read the dependency list from pyproject.toml so there is one source of truth.
DEPS=$(python3 - "$SCRIPT_DIR/pyproject.toml" << 'PYEOF'
import sys, re
text = open(sys.argv[1]).read()
m = re.search(r'\[project\].*?dependencies\s*=\s*\[(.*?)\]', text, re.DOTALL)
if m:
    deps = re.findall(r'"([^"]+)"', m.group(1))
    print(*deps)
PYEOF
)

if [ -z "$DEPS" ]; then
    error "Could not parse dependencies from pyproject.toml"
fi

# shellcheck disable=SC2086
uv pip install --python "$VENV_PYTHON" --quiet $DEPS

# ── 5. Verify gi is importable inside the venv ────────────────────────────
# This should always pass because the venv has --system-site-packages, which
# exposes the system python3-gi.  If it fails something is wrong with the
# system GTK installation.
if ! "$VENV_PYTHON" -c "import gi" 2>/dev/null; then
    error "The venv Python cannot import 'gi' even with system-site-packages.\n       Try: sudo apt-get install --reinstall python3-gi python3-gi-cairo\n       Then re-run this installer."
fi
info "GTK bindings (gi) verified inside the virtual environment."

# ── 6. Install widget script ───────────────────────────────────────────────
info "Copying widget script…"
cp "$SCRIPT_DIR/claude_widget.py" "$INSTALL_DIR/claude_widget.py"
chmod +x "$INSTALL_DIR/claude_widget.py"

# ── 7. Create default config (if missing) ──────────────────────────────────
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
fi
chmod 600 "$CONFIG_FILE"

# ── 8. Autostart desktop entry ─────────────────────────────────────────────
AUTOSTART_FILE="$AUTOSTART_DIR/claude-widget.desktop"
info "Creating autostart entry at $AUTOSTART_FILE…"
cat > "$AUTOSTART_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Claude Usage Widget
Comment=Displays Claude.ai plan usage as a desktop widget
Exec=$VENV_PYTHON $INSTALL_DIR/claude_widget.py
Icon=utilities-system-monitor
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-Cinnamon-Autostart-enabled=true
EOF

# ── 9. Create convenience launcher in PATH ─────────────────────────────────
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
LAUNCHER="$BIN_DIR/claude-widget"
info "Creating launcher at $LAUNCHER…"
cat > "$LAUNCHER" << EOF
#!/usr/bin/env bash
exec "$VENV_PYTHON" "$INSTALL_DIR/claude_widget.py" "\$@"
EOF
chmod +x "$LAUNCHER"

# ── 10. Run first-time setup wizard ────────────────────────────────────────
echo ""
SESSION_KEY=$("$VENV_PYTHON" - << 'PYEOF' 2>/dev/null || true
import json, pathlib, os
cf = pathlib.Path(os.environ.get("CONFIG_FILE", ""))
if cf.exists():
    try:
        print(json.load(cf.open()).get("session_key", ""))
    except Exception:
        pass
PYEOF
)

if [ -z "$SESSION_KEY" ]; then
    info "Running setup wizard…"
    echo ""
    CONFIG_FILE="$CONFIG_FILE" "$VENV_PYTHON" "$INSTALL_DIR/claude_widget.py" --setup
fi

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}✓ Installation complete!${NC}"
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
