# Daemon Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--daemon` flag that detaches the GUI widget from the launching terminal using the Unix double-fork pattern so it runs as a background process with no terminal dependency.

**Architecture:** A module-level `_daemonize()` function performs double-fork + setsid + I/O redirect. `main()` calls it immediately when `--daemon` is present, before any config loading or GTK init. `--daemon` is mutually exclusive with `--tui` and `--dump-api` via an argparse group.

**Tech Stack:** Python stdlib only (`os`, `sys`) — no new dependencies.

---

## File Map

- **Modify:** `claude_widget.py`
  - Add `_daemonize()` module-level function (before `run_setup()`, ~line 1030)
  - Refactor argparse in `main()` to use a mutually-exclusive group for `--daemon`, `--tui`, `--dump-api`
  - Add `--daemon` dispatch at top of `main()` (~line 1335)
  - Update epilog string
- **Modify:** `tests/test_tui.py` — add daemon tests
- **Modify:** `README.md` — document `--daemon`

---

### Task 1: Add tests for `_daemonize`

**Files:**
- Modify: `tests/test_tui.py`

- [ ] **Step 1: Append daemon tests to `tests/test_tui.py`**

Add at the bottom of `tests/test_tui.py`:

```python
def test_daemonize_is_importable():
    import inspect
    import claude_widget
    source = inspect.getsource(claude_widget)
    assert 'def _daemonize' in source


def test_daemonize_double_forks(monkeypatch):
    """
    _daemonize() must fork twice, call setsid, chdir('/'), and redirect I/O.
    We monkeypatch os.fork to avoid actually forking in tests.
    """
    import os
    import claude_widget

    calls = []

    # First fork returns non-zero (parent path) — we want to test the child path,
    # so simulate fork returning 0 (child) both times.
    fork_results = iter([0, 0])
    monkeypatch.setattr(os, 'fork', lambda: next(fork_results))
    monkeypatch.setattr(os, 'setsid', lambda: calls.append('setsid'))
    monkeypatch.setattr(os, 'chdir', lambda p: calls.append(f'chdir:{p}'))

    devnull_fd = open(os.devnull)
    opened_files = []

    original_open = open
    def mock_open(path, *args, **kwargs):
        opened_files.append(path)
        return original_open(os.devnull, *args, **kwargs)

    monkeypatch.setattr('builtins.open', mock_open)

    # _daemonize prints a message then calls sys.exit in the parent paths.
    # With fork returning 0 both times, no sys.exit is called.
    claude_widget._daemonize()

    assert 'setsid' in calls
    assert 'chdir:/' in calls
    # stdin, stdout, stderr redirected — /dev/null opened at least once
    assert any(os.devnull in f or 'widget.log' in f or 'null' in f
               for f in opened_files)
```

- [ ] **Step 2: Run tests — expect `test_daemonize_is_importable` to fail**

```bash
cd /mnt/GAMES_SSD/matt/Code/TripleT-Claude-Widget && .venv/bin/python -m pytest tests/test_tui.py::test_daemonize_is_importable tests/test_tui.py::test_daemonize_double_forks -v 2>&1 | tail -20
```
Expected: both FAIL with ImportError or AttributeError — `_daemonize` not yet defined.

- [ ] **Step 3: Commit**

```bash
git add tests/test_tui.py
git commit -m "test: add _daemonize tests"
```

---

### Task 2: Implement `_daemonize()`

**Files:**
- Modify: `claude_widget.py` — add `_daemonize()` before `run_setup()` (~line 1030)

- [ ] **Step 1: Add `_daemonize()` to `claude_widget.py`**

Insert the following immediately before the `# Setup Wizard (--setup)` section comment:

```python
# ═════════════════════════════════════════════════════════════════════════════
#  Daemon helper  (--daemon)
# ═════════════════════════════════════════════════════════════════════════════

def _daemonize() -> None:
    """
    Detach the process from the controlling terminal using the Unix
    double-fork pattern.  After this function returns, the calling process
    is the grandchild: a background process with no terminal attachment.

    Steps:
      1. Print a user-facing message (before the first fork so it appears).
      2. First fork  — parent exits; child continues.
      3. os.setsid() — child becomes new session leader, loses terminal.
      4. Second fork — grandchild can never re-acquire a terminal.
      5. os.chdir('/') — release any reference to the launch directory.
      6. Redirect stdin → /dev/null, stdout/stderr → LOG_FILE (append).
    """
    print(f"Launching Claude Usage Widget in background…\n"
          f"  Log: {LOG_FILE}\n"
          f"  Stop: pkill -f claude_widget.py")

    # ── First fork ────────────────────────────────────────────────────────
    pid = os.fork()
    if pid > 0:
        sys.exit(0)          # Parent exits — terminal gets its prompt back

    os.setsid()             # Become session leader

    # ── Second fork ───────────────────────────────────────────────────────
    pid = os.fork()
    if pid > 0:
        sys.exit(0)          # Intermediate child exits

    # ── Grandchild: fully detached ────────────────────────────────────────
    os.chdir('/')

    # Redirect standard file descriptors
    with open(os.devnull, 'r') as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())

    log_fh = open(LOG_FILE, 'a')
    os.dup2(log_fh.fileno(), sys.stdout.fileno())
    os.dup2(log_fh.fileno(), sys.stderr.fileno())
    log_fh.close()
```

- [ ] **Step 2: Run the daemonize tests**

```bash
cd /mnt/GAMES_SSD/matt/Code/TripleT-Claude-Widget && .venv/bin/python -m pytest tests/test_tui.py::test_daemonize_is_importable tests/test_tui.py::test_daemonize_double_forks -v 2>&1 | tail -20
```
Expected: both PASS.

- [ ] **Step 3: Run full test suite**

```bash
cd /mnt/GAMES_SSD/matt/Code/TripleT-Claude-Widget && .venv/bin/python -m pytest tests/test_tui.py -v 2>&1
```
Expected: all 9 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add claude_widget.py
git commit -m "feat: add _daemonize() double-fork helper"
```

---

### Task 3: Wire `--daemon` into `main()`

**Files:**
- Modify: `claude_widget.py` — update `main()` at lines 1316–1384

- [ ] **Step 1: Replace the argparse block in `main()` with a mutually-exclusive group**

Locate the current argparse block (lines 1317–1335):

```python
    parser = argparse.ArgumentParser(
        description="Claude.ai Plan Usage Desktop Widget",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 claude_widget.py              Run the widget (default)
  python3 claude_widget.py --tui        Live terminal dashboard (htop-style)
  python3 claude_widget.py --setup      First-time configuration wizard
  python3 claude_widget.py --dump-api   Print raw API JSON (identify field names)
  python3 claude_widget.py --debug      Enable verbose logging
  python3 claude_widget.py --no-curl    Disable curl_cffi (use standard requests)
        """
    )
    parser.add_argument('--setup',    action='store_true', help="Run interactive setup wizard")
    parser.add_argument('--dump-api', action='store_true', help="Print raw API JSON and exit")
    parser.add_argument('--debug',    action='store_true', help="Enable verbose debug logging")
    parser.add_argument('--no-curl',  action='store_true', help="Disable curl_cffi and use requests")
    parser.add_argument('--tui',      action='store_true', help="Run live TUI dashboard in terminal (no GUI)")
    args = parser.parse_args()
```

Replace with:

```python
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
    parser.add_argument('--setup',    action='store_true', help="Run interactive setup wizard")
    parser.add_argument('--debug',    action='store_true', help="Enable verbose debug logging")
    parser.add_argument('--no-curl',  action='store_true', help="Disable curl_cffi and use requests")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--daemon',   action='store_true', help="Detach from terminal and run widget in background")
    mode_group.add_argument('--tui',      action='store_true', help="Run live TUI dashboard in terminal (no GUI)")
    mode_group.add_argument('--dump-api', action='store_true', help="Print raw API JSON and exit")

    args = parser.parse_args()
```

- [ ] **Step 2: Add `--daemon` dispatch at the top of `main()` execution, before config loading**

Locate the block after `args = parser.parse_args()`:

```python
    if args.debug:
        log.setLevel(logging.DEBUG)

    if args.no_curl:
        global HAS_CURL_CFFI
        HAS_CURL_CFFI = False
        log.info("curl_cffi disabled by user flag.")

    if args.setup:
```

Add `--daemon` dispatch immediately after `args = parser.parse_args()` and before the `if args.debug:` block:

```python
    if args.daemon:
        _daemonize()
```

- [ ] **Step 3: Verify `--help` output shows `--daemon` and the mutual-exclusion group**

```bash
cd /mnt/GAMES_SSD/matt/Code/TripleT-Claude-Widget && .venv/bin/python claude_widget.py --help
```
Expected: help output includes `--daemon` with description. Attempting `--daemon --tui` should error:

```bash
.venv/bin/python claude_widget.py --daemon --tui 2>&1
```
Expected: `error: argument --tui: not allowed with argument --daemon`

- [ ] **Step 4: Run full test suite**

```bash
cd /mnt/GAMES_SSD/matt/Code/TripleT-Claude-Widget && .venv/bin/python -m pytest tests/test_tui.py -v 2>&1
```
Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_widget.py
git commit -m "feat: add --daemon flag with mutual exclusion for --tui and --dump-api"
```

---

### Task 4: Update README and push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add `--daemon` to the Usage section**

Locate in `README.md`:
```markdown
```bash
claude-widget                # Start the desktop widget — GUI (default)
claude-widget --tui          # Live terminal dashboard (htop-style, no GUI needed)
```
```

Replace with:
```markdown
```bash
claude-widget                # Start the desktop widget — GUI (default)
claude-widget --daemon       # Start widget detached from terminal (background)
claude-widget --tui          # Live terminal dashboard (htop-style, no GUI needed)
```
```

- [ ] **Step 2: Commit and push**

```bash
git add README.md docs/superpowers/specs/2026-03-28-daemon-mode-design.md docs/superpowers/plans/2026-03-28-daemon-mode.md
git commit -m "docs: document --daemon flag"
git push origin main
```
