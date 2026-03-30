#!/usr/bin/env python3
"""
claude_widget.py — Claude.ai Plan Usage Desktop Widget
=======================================================
Fetches live usage data from Claude.ai's internal API using your
browser session cookie, and renders a compact GTK3 desktop widget
on the Linux Mint / Cinnamon desktop.

Usage:
    python3 claude_widget.py              # Run widget
    python3 claude_widget.py --dump-api   # Print raw API response (for debugging field names)
    python3 claude_widget.py --debug      # Verbose logging
    python3 claude_widget.py --setup      # Interactive setup wizard

Requires:
    python3-gi  python3-requests  python3-dateutil
    gir1.2-gtk-3.0  (usually pre-installed on Linux Mint)

Author: Subnet / Matt
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango
import cairo

import requests
import json
import os
import sys
import threading
import argparse
import logging
import getpass
from datetime import datetime
from pathlib import Path
import time

# ── Try optional imports ─────────────────────────────────────────────────────
try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False


# ═════════════════════════════════════════════════════════════════════════════
#  Configuration
# ═════════════════════════════════════════════════════════════════════════════

CONFIG_DIR  = Path.home() / '.config' / 'claude-widget'
CONFIG_FILE = CONFIG_DIR / 'config.json'
LOG_FILE    = CONFIG_DIR / 'widget.log'

DEFAULT_CONFIG: dict = {
    # ── Required ──────────────────────────────────────────────────────────────
    "session_key":      "",     # Claude.ai 'sessionKey' cookie — see README.md

    # ── Auto-discovered (written back after first run) ────────────────────────
    "org_id":           "",

    # ── Widget behaviour ──────────────────────────────────────────────────────
    "refresh_interval": 300,    # Seconds between background refreshes
    "position_x":       -15,    # Pixels from right edge (negative) or absolute
    "position_y":       50,     # Pixels from top of screen
    "widget_width":     230,    # Fixed pixel width
    "opacity":          0.93,   # 0.0 = transparent, 1.0 = opaque
    "debug":            False,
}


def load_config() -> dict:
    """Load config from disk, merging with defaults for missing keys."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            # Check permissions first
            st = os.stat(CONFIG_FILE)
            if st.st_mode & 0o077:
                log.warning(f"Config file {CONFIG_FILE} has insecure permissions. Fixing...")
                os.chmod(CONFIG_FILE, 0o600)

            with open(CONFIG_FILE) as f:
                stored = json.load(f)
            config.update(stored)
        except Exception as e:
            log.warning(f"Config load error: {e}")
    
    # ── Validation ───────────────────────────────────────────────────────────
    # Ensure refresh interval is not too low (at least 30s)
    ri = config.get('refresh_interval', 300)
    if not isinstance(ri, (int, float)) or ri < 30:
        log.warning(f"Invalid refresh_interval {ri}; resetting to 300s.")
        config['refresh_interval'] = 300
    
    return config


def save_config(config: dict) -> None:
    """Persist config to disk with secure permissions (chmod 600)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    
    # Write to temporary file first then rename for atomic save
    tmp_file = CONFIG_FILE.with_suffix('.tmp')
    with open(tmp_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    os.chmod(tmp_file, 0o600)
    os.replace(tmp_file, CONFIG_FILE)
    log.debug(f"Config saved securely to {CONFIG_FILE}")


# ═════════════════════════════════════════════════════════════════════════════
#  Logging
# ═════════════════════════════════════════════════════════════════════════════

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.chmod(CONFIG_DIR, 0o700)

# Pre-touch log file to set permissions
if not LOG_FILE.exists():
    LOG_FILE.touch(mode=0o600)
else:
    os.chmod(LOG_FILE, 0o600)

logging.basicConfig(
    level   = logging.INFO,
    format  = "[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ]
)
log = logging.getLogger("claude-widget")


# ═════════════════════════════════════════════════════════════════════════════
#  Claude.ai API Client
# ═════════════════════════════════════════════════════════════════════════════

CLAUDE_BASE = "https://claude.ai"

# Mimic a real browser to avoid 403/bot detection
# Modern browsers send "Client Hints" (sec-ch-ua) which are checked by Cloudflare
BROWSER_HEADERS = {
    "User-Agent":       "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "en-US,en;q=0.9",
    "Referer":          "https://claude.ai/chats",
    "Origin":           "https://claude.ai",
    "Sec-CH-UA":        '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Linux"',
    "Sec-Fetch-Dest":   "empty",
    "Sec-Fetch-Mode":   "cors",
    "Sec-Fetch-Site":   "same-origin",
    "DNT":              "1",
    "Upgrade-Insecure-Requests": "1",
    "Connection":       "keep-alive",
}


class ClaudeAPIClient:
    """
    Authenticated client for Claude.ai's internal web API.
    """

    def __init__(self, session_key: str, org_id: str = ""):
        self.session_key = session_key
        self.org_id      = org_id

        # Build a persistent session
        if HAS_CURL_CFFI:
            log.debug("Using curl_cffi for Cloudflare bypass")
            self.session = curl_requests.Session(impersonate="chrome110")
        else:
            log.debug("Using standard requests (curl_cffi not found)")
            self.session = requests.Session()

        self.session.headers.update(BROWSER_HEADERS)
        
        # Explicitly set the cookie
        if HAS_CURL_CFFI:
            self.session.cookies.set('sessionKey', session_key, domain='claude.ai', path='/')
        else:
            jar = requests.cookies.RequestsCookieJar()
            jar.set('sessionKey', session_key, domain='claude.ai', path='/')
            self.session.cookies.update(jar)

    # ── Low-level HTTP ────────────────────────────────────────────────────────

    def _get(self, path: str, timeout: int = 15) -> dict | list | None:
        """GET a Claude.ai API path. Returns parsed JSON or None on error."""
        url = f"{CLAUDE_BASE}{path}"
        try:
            resp = self.session.get(url, timeout=timeout)
            log.debug(f"GET {path} → HTTP {resp.status_code}")
            
            if resp.status_code == 401:
                log.error("401 Unauthorised — session key is invalid or expired.")
                return None
            
            if resp.status_code == 403:
                body_snippet = resp.text[:500].lower()
                if "cloudflare" in body_snippet or "<title>just a moment...</title>" in body_snippet:
                    log.error("403 Forbidden — Blocked by Cloudflare (WAF/Bot detection).")
                    if not HAS_CURL_CFFI:
                        log.error("TIP: curl_cffi is missing. Install it to improve bypass.")
                    log.error("Try refreshing your browser session or check if you are on a VPN.")
                else:
                    log.error(f"403 Forbidden — API rejected the request. (Path: {path})")
                return None

            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            # Catch broader exceptions for curl_cffi compatibility
            if "HTTPError" in str(type(e)) and hasattr(e, 'response'):
                log.error(f"HTTP {e.response.status_code} for {path}")
            elif "ConnectionError" in str(type(e)):
                log.error("Connection error — are you online?")
            elif "Timeout" in str(type(e)):
                log.error(f"Timeout fetching {path}")
            else:
                log.error(f"Request error for {path}: {str(e)[:100]}")
        return None

    # ── Org discovery ─────────────────────────────────────────────────────────

    def discover_org(self) -> str | None:
        """
        Discover the organization UUID from /api/organizations.
        Returns the first org's UUID, or None on failure.
        """
        data = self._get("/api/organizations")
        if not data:
            return None

        # Response may be a list of orgs OR {"organizations": [...]}
        orgs = data if isinstance(data, list) else data.get('organizations', [])
        if not orgs:
            log.error("No organizations found in API response.") # Sanitised
            return None

        org = orgs[0]
        # Field may be 'uuid', 'id', or 'organization_id'
        org_id = org.get('uuid') or org.get('id') or org.get('organization_id')
        if org_id:
            log.info(f"Discovered org_id: {org_id}")
            return org_id

        log.error("Could not extract org_id from organization object.")
        return None

    # ── Usage fetch ───────────────────────────────────────────────────────────

    def fetch_usage(self) -> dict | None:
        """
        Fetch plan usage from Claude.ai. Tries multiple endpoint patterns
        since the internal API may change between deployments.

        Returns a normalised usage dict (see _normalise) or None.
        """
        if not self.org_id:
            log.error("fetch_usage called with no org_id")
            return None

        # Ordered list of endpoints to attempt
        candidates = [
            f"/api/organizations/{self.org_id}/usage",
            f"/api/organizations/{self.org_id}/limits",
            f"/api/organizations/{self.org_id}/entitlements",
            f"/api/organizations/{self.org_id}/billing/usage",
            f"/api/organizations/{self.org_id}",          # Org detail may include limits
        ]

        for ep in candidates:
            data = self._get(ep)
            if data:
                log.debug(f"Got data from {ep}")
                normalised = self._normalise(data, ep)
                if normalised['metrics']:
                    return normalised
                # If no metrics parsed, keep trying other endpoints

        log.error("All usage endpoints returned no parsable data. Run --dump-api to inspect.")
        return None

    def dump_all(self) -> None:
        """
        Print raw JSON from all candidate API endpoints.
        Used with --dump-api flag to identify correct field names.
        """
        print(f"\n{'═'*60}")
        print(f"  Claude.ai API Response Dump  |  org_id: {self.org_id or '(discovering)'}")
        print(f"{'═'*60}\n")

        # Orgs endpoint first
        orgs_data = self._get("/api/organizations")
        print(f"── GET /api/organizations ──")
        print(json.dumps(orgs_data, indent=2))

        if not self.org_id:
            orgs = orgs_data if isinstance(orgs_data, list) else (orgs_data or {}).get('organizations', [])
            if orgs:
                self.org_id = orgs[0].get('uuid') or orgs[0].get('id') or ''

        if self.org_id:
            for ep in [
                f"/api/organizations/{self.org_id}/usage",
                f"/api/organizations/{self.org_id}/limits",
                f"/api/organizations/{self.org_id}/entitlements",
                f"/api/organizations/{self.org_id}/billing/usage",
                f"/api/organizations/{self.org_id}",
            ]:
                print(f"\n── GET {ep} ──")
                data = self._get(ep)
                print(json.dumps(data, indent=2) if data else "  ← No data / error")
        else:
            print("\nERROR: Could not discover org_id. Check session_key.")

    # ── Normalisation ─────────────────────────────────────────────────────────

    def _normalise(self, raw: dict | list, source_ep: str = "") -> dict:
        """
        Convert raw API JSON into a canonical usage structure.
        """
        # If list was returned (e.g. org list), try first item
        if isinstance(raw, list):
            raw = raw[0] if raw else {}

        metrics: list[dict] = []

        # ── New Format: Utilization / Credits (2024/2025) ─────────────────────
        # Some accounts show five_hour, seven_day windows as percentages
        for key, label in [('five_hour', '5h Usage'), ('seven_day', '7d Usage')]:
            data = raw.get(key)
            if isinstance(data, dict) and 'utilization' in data:
                metrics.append({
                    "label":  label,
                    "used":   round(data['utilization'], 1),
                    "limit":  100,
                    "unit":   "%",
                    "period": ""
                })

        # Extra Usage / Credits (Claude for Teams / Pro Extras)
        extra = raw.get('extra_usage')
        if isinstance(extra, dict) and extra.get('is_enabled'):
            metrics.append({
                "label":  "Extra Credits",
                "used":   round(extra.get('used_credits', 0), 0),
                "limit":  round(extra.get('monthly_limit', 0), 0),
                "unit":   "",
                "period": "mo"
            })

        # ── Classic Format: Messages / conversations ──────────────────────────
        MSG_FIELDS = [
            # (used_key, limit_key, label, period)
            ('message_count',           'message_limit',            'Messages',      'day'),
            ('messages_used',           'messages_limit',           'Messages',      'day'),
            ('daily_message_count',     'daily_message_limit',      'Messages',      'day'),
            ('conversation_count',      'conversation_limit',       'Conversations', ''),
            ('claude_pro_message_count','claude_pro_message_limit', 'Messages',      'day'),
        ]
        for used_k, limit_k, label, period in MSG_FIELDS:
            if used_k in raw or limit_k in raw:
                metrics.append({
                    "label":  label,
                    "used":   raw.get(used_k,  0),
                    "limit":  raw.get(limit_k, 0),
                    "unit":   "",
                    "period": period,
                })
                break  # Only one messages row

        # ── Projects ──────────────────────────────────────────────────────────
        PROJ_FIELDS = [
            ('projects_used',  'projects_limit'),
            ('project_count',  'project_limit'),
            ('num_projects',   'max_projects'),
        ]
        for used_k, limit_k in PROJ_FIELDS:
            if used_k in raw or limit_k in raw:
                metrics.append({
                    "label":  "Projects",
                    "used":   raw.get(used_k,  0),
                    "limit":  raw.get(limit_k, 0),
                    "unit":   "",
                    "period": "",
                })
                break

        # ── Storage ───────────────────────────────────────────────────────────
        STORE_FIELDS = [
            ('storage_used_bytes',  'storage_limit_bytes', True),   # True = convert from bytes
            ('storage_used_gb',     'storage_limit_gb',    False),
            ('storage_used',        'storage_limit',       False),
        ]
        for used_k, limit_k, from_bytes in STORE_FIELDS:
            if used_k in raw:
                divisor = 1_073_741_824 if from_bytes else 1
                metrics.append({
                    "label":  "Storage",
                    "used":   round(raw.get(used_k,  0) / divisor, 2),
                    "limit":  round(raw.get(limit_k, 0) / divisor, 2),
                    "unit":   "GB",
                    "period": "",
                })
                break

        # ── Knowledge / context ───────────────────────────────────────────────
        if 'context_window_used' in raw or 'context_tokens_used' in raw:
            k_used  = raw.get('context_window_used') or raw.get('context_tokens_used', 0)
            k_limit = raw.get('context_window_limit') or raw.get('context_tokens_limit', 0)
            if k_limit > 0:
                metrics.append({
                    "label":  "Context",
                    "used":   round(k_used  / 1000, 1),
                    "limit":  round(k_limit / 1000, 1),
                    "unit":   "K",
                    "period": "",
                })

        # ── Fallback: expose any numeric field that looks like a limit ─────────
        if not metrics:
            log.warning(f"No known fields found in response from {source_ep}. "
                        "Run --dump-api to see the raw response.")
            # Heuristic: look for pairs where key contains 'used'/'count' + 'limit'/'max'
            used_keys  = {k: v for k, v in raw.items() if isinstance(v, (int, float))
                          and any(t in k for t in ('used', 'count', 'current'))}
            limit_keys = {k: v for k, v in raw.items() if isinstance(v, (int, float))
                          and any(t in k for t in ('limit', 'max', 'quota', 'total'))}

            for uk, uv in list(used_keys.items())[:4]:
                label = uk.replace('_', ' ').title()
                lv    = 0
                # Try to find a matching limit key
                stem  = uk.replace('_used', '').replace('_count', '').replace('_current', '')
                for lk, lval in limit_keys.items():
                    if stem in lk:
                        lv = lval
                        break
                metrics.append({"label": label, "used": uv, "limit": lv, "unit": "", "period": ""})

        # ── Plan name ─────────────────────────────────────────────────────────
        plan = (raw.get('plan_name')
                or raw.get('plan')
                or raw.get('subscription_plan')
                or raw.get('tier')
                or "Claude")

        # Capitalise nicely: "pro" → "Claude Pro"
        if plan and plan.lower() not in ('claude', 'claude pro', 'claude max', 'free'):
            plan = f"Claude {plan.title()}"

        return {
            "plan":     plan,
            "metrics":  metrics,
            "reset_at": (raw.get('reset_at')
                         or raw.get('resets_at')
                         or (raw.get('seven_day') or {}).get('resets_at')
                         or raw.get('next_reset')
                         or raw.get('period_end')),
        }


# ═════════════════════════════════════════════════════════════════════════════
#  GTK3 Widget
# ═════════════════════════════════════════════════════════════════════════════

# CSS for the widget — dark, compact, purple-accented
WIDGET_CSS = """
/* ── Window shell ─────────────────────────────────────────────────────────── */
window {
    background-color: rgba(12, 11, 18, 0.95);
    border-radius: 10px;
    border: 1px solid rgba(147, 97, 255, 0.25);
}

/* ── Header bar ──────────────────────────────────────────────────────────── */
#header {
    padding: 7px 11px 5px 11px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

#plan-label {
    color: #b07fff;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.4px;
    font-family: "JetBrains Mono", "Fira Mono", monospace;
}

#status-dot {
    color: #22c55e;
    font-size: 8px;
    margin-right: 1px;
}

#status-dot.error {
    color: #ef4444;
}

#refresh-label {
    color: rgba(255, 255, 255, 0.28);
    font-size: 9px;
    font-family: monospace;
}

/* ── Content area ────────────────────────────────────────────────────────── */
#content {
    padding: 6px 11px 9px 11px;
}

/* ── Individual metric rows ─────────────────────────────────────────────── */
#metric-name {
    color: rgba(255, 255, 255, 0.62);
    font-size: 10.5px;
    font-family: "JetBrains Mono", "Fira Mono", monospace;
    margin-top: 5px;
}

#metric-value {
    color: rgba(255, 255, 255, 0.38);
    font-size: 9px;
    font-family: monospace;
}

/* ── Progress bars ───────────────────────────────────────────────────────── */
progressbar {
    margin: 2px 0 0 0;
}

progressbar trough {
    background-color: rgba(255, 255, 255, 0.07);
    border-radius: 3px;
    min-height: 5px;
    border: none;
}

progressbar progress {
    background: linear-gradient(90deg, #7c3aed, #a855f7);
    border-radius: 3px;
    min-height: 5px;
    border: none;
}

progressbar.warn progress {
    background: linear-gradient(90deg, #b45309, #f59e0b);
}

progressbar.crit progress {
    background: linear-gradient(90deg, #b91c1c, #ef4444);
}

/* ── Footer ─────────────────────────────────────────────────────────────── */
#reset-label {
    color: rgba(255, 255, 255, 0.22);
    font-size: 9px;
    font-family: monospace;
    margin-top: 7px;
}

#divider {
    background-color: rgba(255, 255, 255, 0.05);
    min-height: 1px;
    margin: 5px 0;
}

/* ── Error / loading states ─────────────────────────────────────────────── */
#error-label {
    color: #f87171;
    font-size: 10px;
    font-family: monospace;
    padding: 4px 0;
}

#loading-label {
    color: rgba(255, 255, 255, 0.3);
    font-size: 10px;
    font-family: monospace;
    padding: 4px 0;
}
"""


class ClaudeWidget(Gtk.Window):
    """
    Frameless GTK3 window that behaves as a sticky desktop widget.

    Sits below all windows (keep_below), appears on all workspaces (stick),
    and hides from the taskbar. Draggable by left-click-drag. Right-click
    shows a context menu.
    """

    def __init__(self, config: dict):
        super().__init__()
        log.debug("Initializing ClaudeWidget window...")
        self.config   = config
        self.api      = None          # ClaudeAPIClient, set after init
        self.usage    = None          # Last successful usage dict
        self.last_ok  = None          # datetime of last successful fetch
        self._drag_x  = 0             # For window drag tracking
        self._drag_y  = 0

        self._apply_css()
        self._build_ui()
        self._configure_window()
        self._position_window()
        
        log.debug("Calling show_all()...")
        self.show_all()

        # Start background fetch AFTER main loop starts
        # IMPORTANT: Returning False ensures it only runs once.
        # Lack of return False was causing a 100% CPU loop previously.
        GLib.idle_add(lambda: (self._init_api_and_fetch(), False)[1])

        # Periodic refresh timer
        interval = max(60, self.config.get('refresh_interval', 300))
        log.debug(f"Setting refresh timer to {interval}s")
        GLib.timeout_add_seconds(interval, self._on_timer)
        
        # Update "X min ago" label every 60s
        GLib.timeout_add_seconds(60, self._update_age_label)
        
        # Heartbeat to confirm main loop is running
        GLib.timeout_add_seconds(5, self._heartbeat)

    def _heartbeat(self) -> bool:
        log.debug("GTK Main Loop heartbeat (still alive)")
        return True

    # ── CSS ───────────────────────────────────────────────────────────────────

    def _apply_css(self) -> None:
        """Load widget CSS into the Gtk style context."""
        log.debug("Applying CSS...")
        provider = Gtk.CssProvider()
        provider.load_from_data(WIDGET_CSS.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # ── Window configuration ──────────────────────────────────────────────────

    def _configure_window(self) -> None:
        """Set window properties for desktop-widget behaviour."""
        log.debug("Configuring window properties...")
        self.set_title("Claude Usage")
        self.set_decorated(False)           # No titlebar
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)  # Better than DOCK for visibility
        
        # Troubleshooting: Commenting out set_keep_below to ensure visibility.
        # If the widget is hidden behind desktop icons or wallpaper, this is likely why.
        # self.set_keep_below(True)           
        
        self.set_skip_taskbar_hint(True)    # Hidden from taskbar
        self.set_skip_pager_hint(True)      # Hidden from pager / alt-tab
        self.stick()                        # All workspaces

        # Composite / RGBA for rounded corners + transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        else:
            log.warning("RGBA visual not available — transparency will be disabled.")

        self.set_app_paintable(True)
        # Use GtkWidget.set_opacity instead of GtkWindow.set_opacity
        Gtk.Widget.set_opacity(self, self.config.get('opacity', 0.93))

        # Input events for drag + right-click menu
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK   |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect('button-press-event',   self._on_button_press)
        self.connect('button-release-event', self._on_button_release)
        self.connect('motion-notify-event',  self._on_motion)
        self.connect('destroy', Gtk.main_quit)
        self.connect('draw', self._on_draw)

        # Fixed width; height is dynamic
        self.set_size_request(self.config.get('widget_width', 230), -1)

    def _on_draw(self, _widget, cr) -> bool:
        """Paint the window background so the RGBA visual renders visibly."""
        # Check if the visual is actually RGBA before painting with alpha
        visual = self.get_visual()
        is_rgba = visual and visual.get_depth() == 32
        
        if is_rgba:
            cr.set_source_rgba(12/255, 11/255, 18/255, 0.95)
        else:
            cr.set_source_rgb(12/255, 11/255, 18/255)
            
        cr.set_operator(cairo.Operator.SOURCE)
        cr.paint()
        return False

    def _position_window(self) -> None:
        """Position widget using config. Constrains to primary monitor if possible."""
        display = Gdk.Display.get_default()
        if not display:
            log.warning("No display found, moving to (100, 100)")
            self.move(100, 100)
            return

        # Get primary monitor geometry
        primary_monitor = display.get_primary_monitor()
        if not primary_monitor:
            primary_monitor = display.get_monitor(0)
        
        geom = primary_monitor.get_geometry()
        log.info(f"Primary monitor detected: {geom.width}x{geom.height} at {geom.x},{geom.y}")

        px = self.config.get('position_x', -15)
        py = self.config.get('position_y', 50)
        w  = self.config.get('widget_width', 230)

        # Calculate position relative to primary monitor
        # If px is negative, offset from the right edge of the primary monitor
        if px <= 0:
            final_x = geom.x + geom.width + px - w
        else:
            final_x = geom.x + px

        final_y = geom.y + py

        # Safety check: ensure we aren't beyond the virtual desktop's right edge
        # and stay within a reasonable horizontal limit (5120) if requested.
        if final_x > 5120:
            log.warning(f"Calculated X ({final_x}) is beyond 5120. Clamping.")
            final_x = 4800 # Safe spot on a 5120 screen

        log.info(f"Positioning widget at {final_x}, {final_y}")
        self.move(final_x, final_y)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the static widget chrome (header + content placeholder)."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        # ── Header row ────────────────────────────────────────────────────────
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_name("header")

        # Status dot (●) — green when healthy, red on error
        self._dot = Gtk.Label(label="●")
        self._dot.set_name("status-dot")

        # Plan name label
        self._plan_lbl = Gtk.Label(label="◆ Claude")
        self._plan_lbl.set_name("plan-label")
        self._plan_lbl.set_halign(Gtk.Align.START)
        self._plan_lbl.set_hexpand(True)

        # Last-refresh label (right-aligned)
        self._refresh_lbl = Gtk.Label(label="—")
        self._refresh_lbl.set_name("refresh-label")
        self._refresh_lbl.set_halign(Gtk.Align.END)

        header.pack_start(self._dot,        False, False, 0)
        header.pack_start(self._plan_lbl,   True,  True,  0)
        header.pack_end  (self._refresh_lbl, False, False, 0)
        outer.pack_start(header, False, False, 0)

        # ── Content box (rebuilt on each data refresh) ────────────────────────
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.set_name("content")
        outer.pack_start(self._content, True, True, 0)

        self._show_loading()

    # ── Content rendering ─────────────────────────────────────────────────────

    def _clear_content(self) -> None:
        """Remove all dynamic children from the content area."""
        for child in self._content.get_children():
            self._content.remove(child)
            child.destroy()

    def _show_loading(self) -> None:
        self._clear_content()
        lbl = Gtk.Label(label="fetching…")
        lbl.set_name("loading-label")
        lbl.set_halign(Gtk.Align.START)
        self._content.pack_start(lbl, False, False, 0)
        self._content.show_all()

    def _show_error(self, msg: str) -> None:
        """Display an error message in the content area (called from main thread)."""
        log.error("Showing error in widget: %s", msg.replace('\n', ' '))
        self._clear_content()
        self._dot.get_style_context().add_class('error')
        self._dot.get_style_context().remove_class('ok')

        lbl = Gtk.Label(label=msg)
        lbl.set_name("error-label")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(28)
        self._content.pack_start(lbl, False, False, 0)
        self._content.show_all()
        self.resize(1, 1)

    def _render_usage(self, usage: dict) -> None:
        """
        Rebuild content area from a normalised usage dict.
        Always called from the GLib main thread via idle_add.
        """
        log.debug("Rendering usage data to widget")
        self._clear_content()

        # Update header
        plan = usage.get('plan', 'Claude')
        self._plan_lbl.set_text(f"◆ {plan}")
        self._dot.get_style_context().remove_class('error')
        self._dot.get_style_context().add_class('ok')

        metrics = usage.get('metrics', [])
        if not metrics:
            log.warning("No metrics to render")
            lbl = Gtk.Label(label="No usage data found.\nRun --dump-api to inspect.")
            lbl.set_name("error-label")
            lbl.set_line_wrap(True)
            self._content.pack_start(lbl, False, False, 0)
        else:
            for metric in metrics:
                self._add_metric_row(metric)

        # ── Reset timer ───────────────────────────────────────────────────────
        reset_str = self._format_reset(usage.get('reset_at'))
        if reset_str:
            # Divider
            div = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            div.set_name("divider")
            self._content.pack_start(div, False, False, 0)

            rlbl = Gtk.Label(label=reset_str)
            rlbl.set_name("reset-label")
            rlbl.set_halign(Gtk.Align.END)
            self._content.pack_start(rlbl, False, False, 0)

        self._content.show_all()
        # Force a resize to fit content, but ensure we don't vanish
        self.resize(1, 1)
        log.debug(f"Widget rendered and resized. Current size: {self.get_size()}")

    def _add_metric_row(self, metric: dict) -> None:
        """Add one metric row (label + value text + progress bar) to content."""
        label  = metric.get('label', '?')
        used   = metric.get('used',  0)
        limit  = metric.get('limit', 0)
        unit   = metric.get('unit',  '')
        period = metric.get('period', '')

        # ── Label / value row ─────────────────────────────────────────────────
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        name_lbl = Gtk.Label(label=label)
        name_lbl.set_name("metric-name")
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.set_hexpand(True)

        # Format value string
        if limit and limit > 0:
            # Compact: "45/100" or "2.1/5 GB"
            if unit:
                val_str = f"{used}{unit}/{limit}{unit}"
            else:
                val_str = f"{used}/{limit}"
            if period:
                val_str += f" /{period[:1]}"   # "/d" for day
        elif used:
            val_str = f"{used}{unit}"
        else:
            val_str = "—"

        val_lbl = Gtk.Label(label=val_str)
        val_lbl.set_name("metric-value")
        val_lbl.set_halign(Gtk.Align.END)

        row.pack_start(name_lbl, True,  True,  0)
        row.pack_end  (val_lbl,  False, False, 0)
        self._content.pack_start(row, False, False, 0)

        # ── Progress bar ──────────────────────────────────────────────────────
        bar = Gtk.ProgressBar()
        if limit and limit > 0:
            fraction = min(float(used) / float(limit), 1.0)
            bar.set_fraction(fraction)
            ctx = bar.get_style_context()
            if fraction >= 0.90:
                ctx.add_class('crit')
            elif fraction >= 0.75:
                ctx.add_class('warn')
        else:
            bar.set_fraction(0.0)

        self._content.pack_start(bar, False, False, 0)

    @staticmethod
    def _format_reset(reset_at: str | None) -> str:
        return _format_reset(reset_at)

    # ── Data fetching (background threads) ───────────────────────────────────

    def _init_api_and_fetch(self) -> None:
        """Validate config and kick off first background fetch."""
        session_key = self.config.get('session_key', '').strip()
        if not session_key:
            GLib.idle_add(
                self._show_error,
                "No session key.\n"
                "Edit ~/.config/claude-widget/config.json\n"
                "See README.md for instructions."
            )
            return

        self.api = ClaudeAPIClient(
            session_key = session_key,
            org_id      = self.config.get('org_id', ''),
        )
        threading.Thread(target=self._bg_fetch, daemon=True, name="fetch").start()

    def _bg_fetch(self) -> None:
        """
        Background worker: discover org (first run only), then fetch usage.
        Posts results back to the main thread via GLib.idle_add.
        """
        # ── Discover org ID if missing ─────────────────────────────────────
        if not self.api.org_id:
            org_id = self.api.discover_org()
            if not org_id:
                GLib.idle_add(lambda: (self._show_error("Cannot discover org ID.\nIs your session key valid?"), False)[1])
                return
            self.api.org_id        = org_id
            self.config['org_id']  = org_id
            save_config(self.config)

        # ── Fetch usage ───────────────────────────────────────────────────
        usage = self.api.fetch_usage()
        if usage:
            self.usage   = usage
            self.last_ok = datetime.now()
            GLib.idle_add(lambda: (self._render_usage(usage), False)[1])
            GLib.idle_add(lambda: (self._update_age_label(), False)[1])
        else:
            GLib.idle_add(lambda: (self._show_error("Usage fetch failed.\nRun --dump-api for details.\n" f"Log: {LOG_FILE}"), False)[1])

    def _on_timer(self) -> bool:
        """Periodic GLib timer callback — trigger a background refresh."""
        log.debug("Timer refresh triggered")
        self._refresh_lbl.set_text("…")
        if self.api:
            threading.Thread(target=self._bg_fetch, daemon=True, name="refresh").start()
        return True  # Keep timer alive

    def _update_age_label(self) -> bool:
        """Update the 'X min ago' label in the header. Called every 60s."""
        if self.last_ok:
            delta = datetime.now() - self.last_ok
            mins  = int(delta.total_seconds() / 60)
            if mins < 1:
                self._refresh_lbl.set_text("now")
            elif mins < 60:
                self._refresh_lbl.set_text(f"{mins}m ago")
            else:
                h = mins // 60
                self._refresh_lbl.set_text(f"{h}h ago")
        return True  # Keep GLib timer alive (60s interval)

    # ── Window interaction ────────────────────────────────────────────────────

    def _on_button_press(self, widget, event: Gdk.EventButton) -> bool:
        """Handle mouse button press: left=drag start, right=context menu."""
        if event.button == 1:
            # Record position for drag
            self._drag_x = event.x_root - self.get_position()[0]
            self._drag_y = event.y_root - self.get_position()[1]
        elif event.button == 3:
            self._show_context_menu(event)
        return False

    def _on_button_release(self, widget, event: Gdk.EventButton) -> None:
        """On drag end, persist new window position to config."""
        if event.button == 1:
            px, py = self.get_position()
            self.config['position_x'] = px
            self.config['position_y'] = py
            save_config(self.config)

    def _on_motion(self, widget, event: Gdk.EventMotion) -> None:
        """Drag window by left-button motion."""
        if event.state & Gdk.ModifierType.BUTTON1_MASK:
            new_x = int(event.x_root - self._drag_x)
            new_y = int(event.y_root - self._drag_y)
            self.move(max(0, new_x), max(0, new_y))

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        """Right-click context menu with Refresh, Settings and Quit options."""
        menu = Gtk.Menu()

        item_refresh = Gtk.MenuItem(label="↻  Refresh Now")
        item_refresh.connect('activate', self._on_menu_refresh)

        item_settings = Gtk.MenuItem(label="⚙  Settings")
        item_settings.connect('activate', self._show_settings_dialog)

        item_sep = Gtk.SeparatorMenuItem()

        item_quit = Gtk.MenuItem(label="✕  Quit Widget")
        item_quit.connect('activate', lambda _: Gtk.main_quit())

        menu.append(item_refresh)
        menu.append(item_settings)
        menu.append(item_sep)
        menu.append(item_quit)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_menu_refresh(self, _) -> None:
        """Manual refresh via context menu."""
        self._refresh_lbl.set_text("…")
        if self.api:
            threading.Thread(target=self._bg_fetch, daemon=True, name="manual-refresh").start()

    def _show_settings_dialog(self, _=None) -> None:
        """Show a modal settings dialog for position, size, opacity and refresh."""
        dialog = Gtk.Dialog(
            title="Widget Settings",
            transient_for=self,
            modal=True,
            destroy_with_parent=True,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK",     Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_resizable(False)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(8)
        grid.set_margin_top(12)
        grid.set_margin_bottom(12)
        grid.set_margin_start(16)
        grid.set_margin_end(16)

        def _label(text):
            lbl = Gtk.Label(label=text)
            lbl.set_halign(Gtk.Align.START)
            return lbl

        def _spin(value, lo, hi, step=1):
            adj = Gtk.Adjustment(value=value, lower=lo, upper=hi,
                                 step_increment=step, page_increment=10)
            sb  = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
            sb.set_numeric(True)
            return sb

        spin_x = _spin(self.config.get('position_x', -15), -99999, 99999)
        spin_y = _spin(self.config.get('position_y', 50), 0, 99999)
        spin_w = _spin(self.config.get('widget_width', 230), 100, 9999)

        adj_op   = Gtk.Adjustment(value=self.config.get('opacity', 0.93),
                                  lower=0.1, upper=1.0,
                                  step_increment=0.01, page_increment=0.1)
        scale_op = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj_op)
        scale_op.set_digits(2)
        scale_op.set_hexpand(True)
        scale_op.set_size_request(160, -1)

        spin_r = _spin(self.config.get('refresh_interval', 300), 60, 86400)

        rows = [
            (_label("Position X"),    spin_x,   _label("px  (negative = offset from right edge)")),
            (_label("Position Y"),    spin_y,   _label("px")),
            (_label("Widget width"),  spin_w,   _label("px")),
            (_label("Opacity"),       scale_op, None),
            (_label("Refresh every"), spin_r,   _label("seconds  (min 60)")),
        ]
        for row_idx, (lbl, widget, suffix) in enumerate(rows):
            grid.attach(lbl,    0, row_idx, 1, 1)
            grid.attach(widget, 1, row_idx, 1, 1)
            if suffix:
                grid.attach(suffix, 2, row_idx, 1, 1)

        dialog.get_content_area().add(grid)
        dialog.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.config['position_x']       = spin_x.get_value_as_int()
            self.config['position_y']       = spin_y.get_value_as_int()
            self.config['widget_width']     = spin_w.get_value_as_int()
            self.config['opacity']          = round(scale_op.get_value(), 2)
            self.config['refresh_interval'] = max(60, spin_r.get_value_as_int())

            save_config(self.config)
            self._position_window()
            self.set_size_request(self.config['widget_width'], -1)
            Gtk.Widget.set_opacity(self, self.config['opacity'])

        dialog.destroy()


# ═════════════════════════════════════════════════════════════════════════════
#  TUI helpers  (--tui)
# ═════════════════════════════════════════════════════════════════════════════

def _format_reset(reset_at: str | None) -> str:
    """Convert an ISO reset timestamp into a human-readable countdown."""
    if not reset_at:
        return ""
    try:
        if HAS_DATEUTIL:
            dt = dateutil_parser.parse(reset_at)
        else:
            dt = datetime.fromisoformat(reset_at.replace('Z', '+00:00'))

        from datetime import timezone
        now   = datetime.now(dt.tzinfo or timezone.utc)
        delta = dt - now
        secs  = delta.total_seconds()

        if secs <= 0:
            return "Resetting…"
        h, rem = divmod(int(secs), 3600)
        m      = rem // 60
        if h > 23:
            d = h // 24
            return f"Resets in {d}d {h % 24}h"
        return f"Resets in {h}h {m:02d}m"
    except Exception as e:
        log.debug(f"Could not parse reset_at '{reset_at}': {e}")
        return ""


def _bar_style(fraction: float) -> str:
    """Return a rich colour string for a progress fraction."""
    if fraction >= 0.90:
        return "red"
    if fraction >= 0.75:
        return "yellow"
    return "#a855f7"


def _format_age(last_ok) -> str:
    """Return a human-readable 'X min ago' string, or empty string."""
    if not last_ok:
        return ""
    delta = datetime.now() - last_ok
    mins  = int(delta.total_seconds() / 60)
    if mins < 1:
        return "now"
    if mins < 60:
        return f"{mins}m ago"
    return f"{mins // 60}h ago"


def _build_tui_renderable(usage, last_ok, error_msg):
    """
    Build a rich renderable (Panel) from the current usage state.
    Called from the Live render loop on every tick.
    """
    from rich.panel   import Panel
    from rich.text    import Text
    from rich.console import Group

    if error_msg:
        title = Text()
        title.append("● ", style="red")
        title.append("◆ Claude", style="bold #b07fff")
        return Panel(Text(error_msg, style="red"), title=title)

    if usage is None:
        return Panel(Text("fetching…", style="dim"), title="◆ Claude")

    plan    = usage.get('plan', 'Claude')
    age_str = _format_age(last_ok)
    lines   = []

    for metric in usage.get('metrics', []):
        label  = metric.get('label', '?')
        used   = metric.get('used',  0)
        limit  = metric.get('limit', 0)
        unit   = metric.get('unit',  '')
        period = metric.get('period', '')

        # Value string (matches GTK widget format)
        if limit and limit > 0:
            val_str  = f"{used}{unit}/{limit}{unit}" if unit else f"{used}/{limit}"
            if period:
                val_str += f" /{period[:1]}"
            fraction = min(float(used) / float(limit), 1.0)
        else:
            val_str  = f"{used}{unit}" if used else "—"
            fraction = 0.0

        # Label line
        name_line = Text()
        name_line.append(label, style="dim white")
        lines.append(name_line)

        # Progress bar + value line
        filled   = int(fraction * 20)
        bar_text = "█" * filled + "░" * (20 - filled)
        bar_line = Text()
        bar_line.append(bar_text, style=f"bold {_bar_style(fraction)}")
        bar_line.append(f"  {val_str}", style="dim white")
        lines.append(bar_line)

    # Reset countdown footer
    reset_str = _format_reset(usage.get('reset_at'))
    if reset_str:
        lines.append(Text(""))
        footer = Text(justify="right")
        footer.append(reset_str, style="dim white")
        lines.append(footer)

    title = Text()
    title.append("● ", style="green")
    title.append(f"◆ {plan}", style="bold #b07fff")

    return Panel(
        Group(*lines),
        title    = title,
        subtitle = Text(age_str, style="dim") if age_str else None,
    )


def run_tui(config: dict) -> None:
    """
    Live terminal dashboard. Fetches usage on a background thread and
    re-renders every second using rich.live.Live.
    Press Ctrl-C to exit.
    """
    from rich.live import Live

    session_key = config.get('session_key', '').strip()
    client      = ClaudeAPIClient(session_key, org_id=config.get('org_id', ''))

    usage     = None
    last_ok   = None
    error_msg = None
    lock      = threading.Lock()

    def _fetch_loop() -> None:
        nonlocal usage, last_ok, error_msg

        # Discover org ID on first run
        if not client.org_id:
            org_id = client.discover_org()
            if not org_id:
                with lock:
                    error_msg = ("Cannot discover org ID.\n"
                                 "Is your session key valid?\n"
                                 "Run --dump-api for details.")
                return
            client.org_id    = org_id
            config['org_id'] = org_id
            save_config(config)

        while True:
            result = client.fetch_usage()
            with lock:
                if result:
                    usage     = result
                    last_ok   = datetime.now()
                    error_msg = None
                else:
                    error_msg = "Usage fetch failed.\nRun --dump-api for details."
            time.sleep(max(60, config.get('refresh_interval', 300)))

    threading.Thread(target=_fetch_loop, daemon=True, name="tui-fetch").start()

    try:
        with Live(_build_tui_renderable(None, None, None),
                  refresh_per_second=1, screen=True) as live:
            while True:
                with lock:
                    u, lo, em = usage, last_ok, error_msg
                live.update(_build_tui_renderable(u, lo, em))
                time.sleep(1)
    except KeyboardInterrupt:
        pass


# ═════════════════════════════════════════════════════════════════════════════
#  Daemon helper  (--daemon)
# ═════════════════════════════════════════════════════════════════════════════

def _daemonize() -> None:
    """
    Launch a fully-detached subprocess running the widget and exit.

    Forking the current process is unsafe for GTK apps: GDK has already
    opened a socket to the X server, and duplicating that connection across
    fork boundaries causes the window to never render.  Instead we spawn a
    brand-new Python process (clean GTK state) with start_new_session=True
    (equivalent to setsid) and redirect its I/O to the log file.
    """
    import subprocess

    print(f"Launching Claude Usage Widget in background…\n"
          f"  Log: {LOG_FILE}\n"
          f"  Stop: pkill -f claude_widget.py")

    # Build argv without --daemon so the child runs as a normal GUI widget
    argv = [a for a in sys.argv if a != '--daemon']

    log_fh = open(LOG_FILE, 'a')
    subprocess.Popen(
        argv,
        start_new_session=True,   # setsid — detaches from terminal
        stdin=subprocess.DEVNULL,
        stdout=log_fh,
        stderr=log_fh,
        close_fds=True,
    )
    log_fh.close()
    sys.exit(0)


# ═════════════════════════════════════════════════════════════════════════════
#  Setup Wizard (--setup)
# ═════════════════════════════════════════════════════════════════════════════

def run_setup() -> None:
    """Interactive CLI setup wizard to create the initial config.json."""
    print("\n╔════════════════════════════════════════╗")
    print("║   Claude Usage Widget — Setup Wizard   ║")
    print("╚════════════════════════════════════════╝\n")
    print("To authenticate, you need your Claude.ai session cookie.\n")
    print("Steps:")
    print("  1. Open https://claude.ai in your browser")
    print("  2. Press F12 → Application tab → Cookies → https://claude.ai")
    print("  3. Find 'sessionKey' and copy the Value\n")

    try:
        raw_key = getpass.getpass("Paste your sessionKey value (input hidden): ").strip()
        if not raw_key:
            print("ERROR: No session key entered. Aborting.")
            sys.exit(1)
        
        # Security feedback: show length and first/last char to confirm paste worked
        print(f"✓ Received key ({len(raw_key)} chars). Ends with ...{raw_key[-4:] if len(raw_key) > 4 else '****'}")
        session_key = raw_key
    except EOFError:
        print("\nERROR: Input cancelled.")
        sys.exit(1)

    config = DEFAULT_CONFIG.copy()
    config['session_key'] = session_key

    pos_ans = input("Widget position — top-right corner? [Y/n]: ").strip().lower()
    if pos_ans == 'n':
        try:
            config['position_x'] = int(input("  X position (px from left): "))
            config['position_y'] = int(input("  Y position (px from top):  "))
        except ValueError:
            print("  Invalid input; using default position.")

    save_config(config)
    print(f"\n✓ Config saved to {CONFIG_FILE}")
    print("  Run:  python3 claude_widget.py\n")


# ═════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Claude.ai Plan Usage Desktop Widget",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 claude_widget.py              Run the widget (default)
  python3 claude_widget.py --daemon     Run widget detached from terminal (background)
  python3 claude_widget.py --tui        Live terminal dashboard (htop-style)
  python3 claude_widget.py --setup      First-time configuration wizard
  python3 claude_widget.py --dump-api   Print raw API JSON (identify field names)
  python3 claude_widget.py --debug      Enable verbose logging
  python3 claude_widget.py --no-curl    Disable curl_cffi (use standard requests)
        """
    )
    parser.add_argument('--setup',   action='store_true', help="Run interactive setup wizard")
    parser.add_argument('--debug',   action='store_true', help="Enable verbose debug logging")
    parser.add_argument('--no-curl', action='store_true', help="Disable curl_cffi and use requests")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--daemon',   action='store_true', help="Detach from terminal and run widget in background")
    mode_group.add_argument('--tui',      action='store_true', help="Run live TUI dashboard in terminal (no GUI)")
    mode_group.add_argument('--dump-api', action='store_true', help="Print raw API JSON and exit")

    args = parser.parse_args()

    if args.daemon:
        _daemonize()

    if args.debug:
        log.setLevel(logging.DEBUG)

    if args.no_curl:
        global HAS_CURL_CFFI
        HAS_CURL_CFFI = False
        log.info("curl_cffi disabled by user flag.")

    if args.setup:
        run_setup()
        sys.exit(0)

    # Ensure config exists and is valid
    if not CONFIG_FILE.exists():
        print(f"No config found at {CONFIG_FILE}")
        run_setup()
        sys.exit(0)

    config = load_config()
    
    # Check if session key is empty
    if not config.get('session_key', '').strip():
        print(f"ERROR: Session key is empty in {CONFIG_FILE}")
        run_setup()
        sys.exit(0)

    if args.debug:
        config['debug'] = True

    if args.dump_api:
        # Dump mode: print raw API responses and exit (no GUI)
        session_key = config.get('session_key', '').strip()
        log.setLevel(logging.DEBUG)
        client = ClaudeAPIClient(session_key, org_id=config.get('org_id', ''))
        if not client.org_id:
            client.org_id = client.discover_org() or ''
        client.dump_all()
        sys.exit(0)

    if args.tui:
        run_tui(config)
        sys.exit(0)

    # ── Launch widget ─────────────────────────────────────────────────────────
    log.info(f"Starting Claude Usage Widget (refresh every {config.get('refresh_interval', 300)}s)")
    widget = ClaudeWidget(config)
    Gtk.main()
    log.info("Widget exited.")


if __name__ == '__main__':
    main()
