# Settings Dialog — Design Spec
Date: 2026-03-28

## Overview

Add a GUI settings dialog to the GTK widget, accessible via the right-click context menu. Allows users to adjust position, size, opacity, and refresh interval without editing `config.json` directly.

## Architecture

A single new method `_show_settings_dialog()` added to `ClaudeWidget`. The right-click context menu gets a new "⚙  Settings" item. No new files or classes.

```
Right-click menu
  ├── ↻  Refresh Now      (existing)
  ├── ⚙  Settings         ← NEW → _show_settings_dialog()
  ├── ─────────────────   (existing separator)
  └── ✕  Quit Widget      (existing)
```

## Dialog Layout

`Gtk.Dialog` (modal) with a two-column grid (`Gtk.Grid`):

```
┌─ Settings ──────────────────────────────┐
│                                         │
│  Position X     [    -15  ↑↓]  px       │
│  Position Y     [     50  ↑↓]  px       │
│  Widget width   [    230  ↑↓]  px       │
│  Opacity        [━━━━━━━━━━━━━]  0.93   │
│  Refresh every  [    300  ↑↓]  seconds  │
│                                         │
│  [  Cancel  ]             [  OK  ]      │
└─────────────────────────────────────────┘
```

### Input widgets

| Setting | Widget | Constraints |
|---------|--------|-------------|
| Position X | `Gtk.SpinButton` (int) | No min/max. Note shown: "Negative = offset from right edge" |
| Position Y | `Gtk.SpinButton` (int) | Min 0 |
| Widget width | `Gtk.SpinButton` (int) | Min 100 |
| Opacity | `Gtk.Scale` (float) | 0.0–1.0, 2 decimal places |
| Refresh interval | `Gtk.SpinButton` (int) | Min 60 (matches existing validation) |

All inputs pre-populated from current `self.config` values on open.

## Applying Changes (OK pressed)

1. Read values from all input widgets
2. Write to `self.config`
3. Call `save_config(self.config)`
4. Call `_position_window()` — widget moves immediately
5. Call `self.set_size_request(width, -1)` — width applies immediately
6. Call `Gtk.Widget.set_opacity(self, opacity)` — opacity applies immediately
7. Refresh interval takes effect on the next timer tick

Cancel discards all changes with no side effects.

## Files Changed

- `claude_widget.py` — add `_show_settings_dialog()` to `ClaudeWidget`, add menu item to `_show_context_menu()`
