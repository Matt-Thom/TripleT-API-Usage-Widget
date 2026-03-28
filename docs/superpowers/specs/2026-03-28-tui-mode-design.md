# TUI Live Mode — Design Spec
Date: 2026-03-28

## Overview

Add a `--tui` flag to `claude_widget.py` that launches a live-updating terminal dashboard displaying the same Claude.ai plan usage data as the GTK widget. The GUI remains the default; `--tui` is an explicit opt-in.

## Architecture

The existing code structure is preserved entirely. One new function `run_tui(config)` is added alongside `ClaudeWidget`. The `main()` dispatch gains one branch:

```
main()
  ├── --setup     → run_setup()
  ├── --dump-api  → client.dump_all()
  ├── --tui       → run_tui(config)   ← NEW
  └── (default)   → ClaudeWidget + Gtk.main()
```

No changes to `ClaudeAPIClient`, `_normalise()`, config loading, or the GTK widget.

## TUI Rendering

Uses `rich.live.Live` with a `rich.panel.Panel` containing a `rich.console.Group` of rows.

Layout:

```
┌─ ● ◆ Claude Pro ─────────────────────────────┐
│ Messages                                       │
│ ████████████░░░░░░░░  45/100 /day              │
│ Projects                                       │
│ ███░░░░░░░░░░░░░░░░░  3/20                     │
│ Storage                                        │
│ ████████░░░░░░░░░░░░  2.1/5 GB                 │
│                          Resets in 4h 23m      │
└────────────────────────────────────────────────┘
```

- Panel title: `● ◆ <plan name>` + last-fetch age (e.g. `2m ago`) right-aligned in subtitle
- One label + progress bar per metric
- Progress bar colours: purple (ok) → amber (≥75%) → red (≥90%), matching GTK widget thresholds
- Footer line: right-aligned reset countdown recalculated on every redraw tick
- On error: panel body replaced with error message; retries on next interval

## Data Flow

- Background thread calls `ClaudeAPIClient.fetch_usage()` on `refresh_interval` (from config)
- Result stored in a shared variable; `rich.live.Live` redraws at 1s tick using latest data
- Initial fetch happens immediately on startup
- Thread-safety: single writer (fetch thread), single reader (render tick) — a simple lock or `threading.Event` is sufficient

## Dependencies

- Add `rich` to `pyproject.toml` dependencies

## Flags

- `--tui` added to `argparse` in `main()`
- Compatible with `--debug` (verbose logging still goes to `widget.log`; stdout is owned by rich)
- Compatible with `--no-curl`
- Mutually exclusive with `--dump-api` (both are non-GUI non-widget modes; argparse group enforces this)

## Exit

- `Ctrl-C` exits cleanly via `rich.live.Live` context manager
- No persistent state changes on exit

## Files Changed

- `claude_widget.py` — add `run_tui()`, add `--tui` argparse flag
- `pyproject.toml` — add `rich` dependency
