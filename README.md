# Claude Usage Widget

A compact, live desktop widget for **Linux Mint / Cinnamon** that polls Claude.ai's internal API and displays your plan usage — messages, projects, storage, and reset timer — as an always-visible overlay on your desktop background.

---

## Preview

```
● ◆ Claude Pro              2m ago
────────────────────────────────
Messages
[███████████░░░░░░] 45/100 /d
Projects
[███░░░░░░░░░░░░░░] 3/20
Storage
[████████░░░░░░░░░] 2.1/5GB
────────────────────────────────
                Resets in 4h 23m
```

Features:
- **Compact** — one progress bar per metric, no wasted space
- **Colour-coded** — purple (ok) → amber (≥75%) → red (≥90%)
- **Draggable** — left-click-drag to reposition; position auto-saved
- **Right-click menu** — Refresh Now / Quit
- **Auto-refresh** every 5 minutes (configurable)
- **Autostart** at login via `.desktop` entry

---

## Installation

### Recommended (System-wide)
```bash
cd claude-widget
bash install.sh
```

The installer:
1.  Installs system dependencies (`python3-gi`, `python3-venv`, `python3-pip`, `gir1.2-gtk-3.0`).
2.  Creates a secure virtual environment in `~/.local/share/claude-widget/venv`.
3.  Enforces strict file permissions (`chmod 700` on config dir, `chmod 600` on `config.json`).
4.  Adds an autostart entry for your desktop environment.
5.  Runs the secure setup wizard to collect your session key.

### Local Development / Portable
If you prefer not to install the widget system-wide, you can run it directly from the project directory:
```bash
bash start_local.sh
```
This script creates a local `.venv`, installs dependencies, and launches the widget without modifying your system paths or autostart entries.

---

## Getting Your Session Key

Claude.ai authenticates via a browser session cookie named **`sessionKey`**.

1.  Open [https://claude.ai](https://claude.ai) and sign in.
2.  Press **F12** to open DevTools.
3.  Go to the **Application** tab → **Storage** → **Cookies** → `https://claude.ai`.
4.  Find the row named `sessionKey` and copy the **Value** column.

> **Security Note:** This key grants full access to your Claude account.
> - The setup wizard uses a masked input (input hidden) to prevent the key from being seen or logged.
> - The widget automatically secures `~/.config/claude-widget/config.json` with `chmod 600`.
> - Never share this key or commit it to version control.

---

## Configuration

Edit `~/.config/claude-widget/config.json`:

```json
{
  "session_key":      "sk-ant-...",   // Your Claude.ai sessionKey cookie
  "org_id":           "",             // Auto-discovered on first run; or set manually
  "refresh_interval": 300,            // Seconds between background refreshes
  "position_x":       -15,            // Negative = offset from right edge of screen
  "position_y":       50,             // Pixels from top of screen
  "widget_width":     230,            // Fixed pixel width
  "opacity":          0.93,           // 0.0–1.0
  "debug":            false           // Verbose logging to widget.log
}
```

| Key | Default | Notes |
|-----|---------|-------|
| `position_x` | `-15` | Negative values offset from the **right** edge. `0` = far left. |
| `position_y` | `50` | Pixels from the top of the primary monitor. |
| `refresh_interval` | `300` | Minimum recommended: 60 (avoid rate-limiting). |

After editing config, restart the widget:
```bash
pkill -f claude_widget.py && claude-widget &
```

---

## Usage

```bash
claude-widget                # Start the widget — GUI (default)
claude-widget --tui          # Live terminal dashboard (htop-style, no GUI needed)
claude-widget --dump-api     # Print raw API JSON from all endpoints (debugging)
claude-widget --setup        # Re-run setup wizard
claude-widget --debug        # Verbose logging to stdout + widget.log
```

### Debugging field names

Claude.ai's internal API is undocumented. If the widget shows "No usage data found", run:

```bash
claude-widget --dump-api
```

This prints the raw JSON from every candidate endpoint. Look for fields that contain your usage numbers, then update the `_normalise()` method in `claude_widget.py` to map them correctly.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No session key" error | Config not set up | Run `claude-widget --setup` |
| "401 Unauthorised" | Session key expired | Get a fresh sessionKey from browser |
| "Cannot discover org ID" | Session key invalid or network blocked | Check key; try `--dump-api` |
| "No usage data found" | API field names changed | Run `--dump-api`, update `_normalise()` |
| Widget appears behind desktop icons | Compositor issue | Try toggling `set_keep_below` in code |
| Widget not starting at login | Autostart entry missing | Re-run `install.sh` |

Logs: `~/.config/claude-widget/widget.log`

---

## File Locations

| Path | Purpose |
|------|---------|
| `~/.local/share/claude-widget/claude_widget.py` | Widget script |
| `~/.config/claude-widget/config.json` | User config |
| `~/.config/claude-widget/widget.log` | Runtime log |
| `~/.config/autostart/claude-widget.desktop` | Autostart entry |
| `~/.local/bin/claude-widget` | CLI launcher |

---

## Notes

- **API stability:** Claude.ai's internal API is not officially documented and may change. The widget tries multiple endpoint patterns and includes a `--dump-api` diagnostic to recover from changes.
- **Rate limiting:** The default 5-minute refresh interval is conservative. Reduce with care.
- **Session expiry:** The `sessionKey` cookie has a long TTL but will eventually expire. The widget will show a 401 error when it does — just update the config with a fresh key.
- **Multi-monitor:** The widget positions relative to the default Gdk screen. For multi-monitor setups, adjust `position_x`/`position_y` manually in config.

---

## Dependencies

- `python3-gi` — PyGObject (GTK3 bindings) — GUI mode only
- `python3-requests` — HTTP client
- `python3-dateutil` — ISO timestamp parsing (optional but recommended)
- `gir1.2-gtk-3.0` — GTK3 typelib — GUI mode only
- `rich` — Terminal rendering for `--tui` mode

All available via `apt` on Linux Mint 22.x (`python3-gi`, system deps); `rich` installed via pip/uv.
