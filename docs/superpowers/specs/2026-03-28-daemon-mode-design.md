# Daemon Mode — Design Spec
Date: 2026-03-28

## Overview

Add a `--daemon` flag that detaches the GUI widget from the launching terminal using the standard Unix double-fork pattern. The terminal returns immediately; the widget continues running as a background process with no terminal dependency.

## Architecture

A module-level `_daemonize()` function is called at the very top of `main()` when `--daemon` is passed, before config loading or GTK initialisation. The forked grandchild process continues with the normal GTK launch path.

```
main()
  ├── --daemon flag present? → _daemonize()  ← NEW
  ├── --setup     → run_setup()
  ├── --dump-api  → client.dump_all()
  ├── --tui       → run_tui(config)
  └── (default)   → ClaudeWidget + Gtk.main()
```

`--daemon` is mutually exclusive with `--tui` and `--dump-api` (enforced by argparse).

## `_daemonize()` Implementation

Standard Unix double-fork:

1. Print: `Launching Claude Usage Widget in background… (log: ~/.config/claude-widget/widget.log)`
2. **First fork** — parent calls `sys.exit(0)`, child continues
3. **`os.setsid()`** — child becomes session leader, detaches from controlling terminal
4. **Second fork** — grandchild can never re-acquire a controlling terminal; intermediate child exits
5. **`os.chdir('/')`** — prevent daemon from holding a lock on the working directory
6. **Redirect I/O** — stdin → `/dev/null`; stdout and stderr → `LOG_FILE` (append mode)

After `_daemonize()` returns, the grandchild continues into normal `main()` execution (config load → GTK launch).

## Argparse Changes

- Add `--daemon` flag
- Mutually exclusive group covering `--daemon`, `--tui`, `--dump-api`

## Files Changed

- `claude_widget.py` — add `_daemonize()`, add `--daemon` argparse flag, add mutual-exclusion group
- `README.md` — document `--daemon` in usage section
