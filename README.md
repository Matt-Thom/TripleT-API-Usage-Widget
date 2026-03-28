# TripleT Claude Usage Widget

Monitor your Claude.ai plan usage at a glance. Displays live message counts, project usage, storage, and your reset timer — either as an always-on desktop widget or a live terminal dashboard.

Built for **Linux Mint / Cinnamon** but works on any Linux desktop with GTK3.

---

## Modes

### GUI Widget
A frameless, always-visible overlay that sits on your desktop background. Stays below all windows, appears on every workspace, and hides from the taskbar.

```
● ◆ Claude Pro                        2m ago
────────────────────────────────────────────
Messages
████████████░░░░░░░░  45/100 /day
Projects
███░░░░░░░░░░░░░░░░░  3/20
Storage
████████░░░░░░░░░░░░  2.1/5 GB
────────────────────────────────────────────
                           Resets in 4h 23m
```

### TUI Dashboard (`--tui`)
A live terminal dashboard in the style of `htop`. Runs in any terminal — no desktop environment required.

```
╭─ ● ◆ Claude Pro ──────────────────── 2m ago ─╮
│ Messages                                       │
│ ████████████░░░░░░░░  45/100 /day              │
│ Projects                                       │
│ ███░░░░░░░░░░░░░░░░░  3/20                     │
│ Storage                                        │
│ ████████░░░░░░░░░░░░  2.1/5 GB                 │
│                           Resets in 4h 23m     │
╰────────────────────────────────────────────────╯
```

Both modes share the same colour coding: **purple** (ok) → **amber** (≥75%) → **red** (≥90%).

---

## Installation

### Recommended (system-wide, with autostart)

```bash
git clone git@github.com:Matt-Thom/TripleT-API-Usage-Widget.git
cd TripleT-API-Usage-Widget
bash install.sh
```

The installer:
1. Installs system dependencies (`python3-gi`, `python3-venv`, `python3-pip`, `gir1.2-gtk-3.0`)
2. Creates a virtual environment at `~/.local/share/claude-widget/venv` and installs Python deps
3. Secures the config directory (`chmod 700`) and config file (`chmod 600`)
4. Adds an autostart `.desktop` entry so the widget launches at login
5. Runs the setup wizard to collect your session key

### Local / portable (no system changes)

```bash
bash start_local.sh
```

Creates a local `.venv`, installs dependencies, and launches the widget from the project directory. Nothing is written outside the repo.

---

## Getting Your Session Key

Claude.ai authenticates via a browser session cookie named **`sessionKey`**.

1. Open [https://claude.ai](https://claude.ai) and sign in
2. Press **F12** → **Application** tab → **Storage** → **Cookies** → `https://claude.ai`
3. Find the row named `sessionKey` and copy the **Value** column

> **Security note:** This key grants full access to your Claude account.
> - The setup wizard masks input so the key is never echoed to the terminal or logged
> - Config is automatically secured with `chmod 600`
> - Never share this key or commit it to version control

---

## Usage

```bash
claude-widget                # Start the desktop widget — GUI (default)
claude-widget --tui          # Live terminal dashboard (htop-style, no GUI needed)
claude-widget --setup        # First-time setup / re-configure session key
claude-widget --dump-api     # Print raw API JSON for all endpoints (debugging)
claude-widget --debug        # Verbose logging to stdout and widget.log
claude-widget --no-curl      # Disable curl_cffi, fall back to standard requests
```

**TUI controls:** Press `Ctrl-C` to exit. Refreshes automatically on the configured interval.

**GUI controls:** Left-click-drag to reposition (position is saved). Right-click for Refresh / Quit.

---

## Configuration

Config is stored at `~/.config/claude-widget/config.json` and created automatically by `--setup`.

```json
{
  "session_key":      "sk-ant-...",
  "org_id":           "",
  "refresh_interval": 300,
  "position_x":       -15,
  "position_y":       50,
  "widget_width":     230,
  "opacity":          0.93,
  "debug":            false
}
```

| Key | Default | Notes |
|-----|---------|-------|
| `session_key` | — | Your Claude.ai `sessionKey` cookie. Required. |
| `org_id` | `""` | Auto-discovered on first run. Can be set manually. |
| `refresh_interval` | `300` | Seconds between refreshes. Minimum: 60. |
| `position_x` | `-15` | Negative = offset from the right edge of the screen. |
| `position_y` | `50` | Pixels from the top of the screen. |
| `widget_width` | `230` | Fixed width in pixels (GUI only). |
| `opacity` | `0.93` | Window opacity 0.0–1.0 (GUI only). |
| `debug` | `false` | Verbose logging to `widget.log`. |

After editing config, restart:
```bash
pkill -f claude_widget.py && claude-widget &
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No session key" | Config not set up | Run `claude-widget --setup` |
| "401 Unauthorised" | Session key expired | Get a fresh `sessionKey` from your browser |
| "Cannot discover org ID" | Invalid key or network issue | Check the key; try `--dump-api` |
| "No usage data found" | API field names changed | Run `--dump-api`, update `_normalise()` in `claude_widget.py` |
| Widget behind desktop icons | Compositor issue | Toggle `set_keep_below` in the source |
| Widget not starting at login | Autostart entry missing | Re-run `install.sh` |
| Cloudflare 403 error | Bot detection | Install `curl_cffi` (`pip install curl_cffi`) or refresh your browser session |

Logs: `~/.config/claude-widget/widget.log`

**If the API fields change:** Claude.ai's internal API is undocumented and may change between deployments. Run `--dump-api` to print the raw JSON from every candidate endpoint, then update the field mappings in `_normalise()`.

---

## File Locations

| Path | Purpose |
|------|---------|
| `~/.local/share/claude-widget/claude_widget.py` | Installed widget script |
| `~/.config/claude-widget/config.json` | User config (chmod 600) |
| `~/.config/claude-widget/widget.log` | Runtime log |
| `~/.config/autostart/claude-widget.desktop` | Login autostart entry |
| `~/.local/bin/claude-widget` | CLI launcher |

---

## Dependencies

| Package | Purpose | Required for |
|---------|---------|-------------|
| `python3-gi` | PyGObject — GTK3 bindings | GUI mode |
| `gir1.2-gtk-3.0` | GTK3 typelib | GUI mode |
| `requests` | HTTP client | Both modes |
| `python-dateutil` | ISO timestamp parsing | Both modes (optional) |
| `curl_cffi` | Cloudflare-bypass HTTP | Both modes (optional but recommended) |
| `rich` | Terminal rendering | TUI mode |

System packages (`python3-gi`, `gir1.2-gtk-3.0`) are installed by `install.sh` via `apt`. Python packages are managed via `uv` / pip inside the virtual environment.

---

## Notes

- **API stability:** Claude.ai's internal API is undocumented and may change without notice. The widget tries multiple endpoint patterns automatically and `--dump-api` helps recover when they do.
- **Rate limiting:** The default 5-minute refresh is conservative. Lower values risk rate-limiting from Claude.ai.
- **Session expiry:** The `sessionKey` cookie has a long TTL but will eventually expire. Re-run `--setup` when you see a 401 error.
- **Multi-monitor (GUI):** The widget positions relative to the total virtual desktop width. Adjust `position_x` / `position_y` in config for non-standard setups.
