# Cross-Platform Expansion Plan: macOS & Windows Support

## Objective
Expand the Claude Usage Widget to support macOS and Windows while maintaining a single, clean codebase. The goal is to provide a "native-feeling" widget experience on all platforms without breaking the existing Linux implementation.

## Key Challenges & Context
- **GUI Framework:** Current GTK3 implementation is tailored for Linux (X11/Wayland). macOS and Windows support for GTK3 can be difficult to set up and may not support "frameless, sticky desktop widgets" reliably.
- **File Paths:** Config and log paths currently use Linux-specific patterns (`~/.config`).
- **Autostart:** Uses `.desktop` files (Linux-only). macOS requires `LaunchAgents` (plist), and Windows typically uses the `Startup` folder or Registry.
- **Dependencies:** `python3-gi` and `gir1.2-gtk-3.0` are system-level packages on Linux. macOS and Windows will need different ways to manage these or an alternative toolkit.

---

## Proposed Strategy: Hybrid/Adapter Approach

### 1. Unified Backend, Modular Frontend
Keep the `ClaudeAPIClient` and normalisation logic shared. Extract the GUI logic into a base class or use platform-specific subclasses if GTK3 proves too difficult on macOS/Windows.

### 2. GUI Path Decisions
- **Option A (Multi-GTK):** Attempt to make GTK3 work on all platforms. 
  - *Pros:* Code reuse.
  - *Cons:* Hard for users to install (requires Homebrew/MSYS2), looks non-native.
- **Option B (Flet / Webview):** Re-implement the GUI using [Flet](https://flet.dev/) (Flutter-based) or a lightweight Webview.
  - *Pros:* True cross-platform, easy installation, native-feeling frameless windows.
  - *Cons:* Requires a GUI rewrite.
- **Recommendation:** Stick with GTK3/GObject for now as a "v1" cross-platform goal, but abstract the **Autostart** and **File Path** logic immediately. If GTK3 fails on macOS/Windows, pivot to **Flet** for those platforms while keeping GTK for Linux.

---

## Implementation Phases

### Phase 1: Platform Abstraction (Refactoring)
- **File Paths:** Update `CONFIG_DIR` to use `platformdirs` or a custom `get_app_dir()` function.
  - Linux: `~/.config/claude-widget`
  - macOS: `~/Library/Application Support/claude-widget`
  - Windows: `%APPDATA%\claude-widget`
- **Constants:** Create a `PLATFORM` constant (`sys.platform`).

### Phase 2: macOS Support
- **Installation:** Create a `Brewfile` or `install_macos.sh`.
- **GUI:** 
  - Test GTK3 via Homebrew (`brew install gtk+3 gobject-introspection`).
  - Handle macOS "Window Level" (making it stay on the desktop).
- **Autostart:** Implement `.plist` generation for `~/Library/LaunchAgents`.

### Phase 3: Windows Support
- **Installation:** Create `install_windows.ps1`.
- **GUI:** 
  - Test GTK3 via MSYS2 or `gvsbuild`.
  - Alternative: Implement a minimal TRAY icon for Windows if the widget overlay is too complex.
- **Autostart:** Implement a shortcut in `shell:startup`.

### Phase 4: Unified Installer
- Replace `install.sh` with a Python-based `install.py` that detects the OS and performs the correct steps.
- Leverage `uv` for cross-platform dependency management.

---

## Verification & Testing
- **Linux:** Ensure no regressions in Mint/Cinnamon.
- **macOS:** Test on Intel and Apple Silicon. Verify "Keep Below" behavior.
- **Windows:** Test on Windows 10/11. Verify transparency and position saving.

## Migration & Rollback
- Existing Linux users should see their config moved to a more standard location (optional but recommended).
- Keep the original `install.sh` as a legacy shim for one version.
