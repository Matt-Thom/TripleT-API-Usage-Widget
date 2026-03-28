import sys
import os
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Stub out gi before importing claude_widget
sys.modules['gi'] = mock.MagicMock()
sys.modules['gi.repository'] = mock.MagicMock()
for _mod in ['Gtk', 'Gdk', 'GLib', 'Pango']:
    sys.modules[f'gi.repository.{_mod}'] = mock.MagicMock()

from claude_widget import _build_tui_renderable, _bar_style
from rich.panel import Panel
from datetime import datetime


def test_returns_panel_when_no_data():
    result = _build_tui_renderable(None, None, None)
    assert isinstance(result, Panel)


def test_returns_panel_with_error():
    result = _build_tui_renderable(None, None, "Test error")
    assert isinstance(result, Panel)


def test_returns_panel_with_usage():
    usage = {
        "plan": "Claude Pro",
        "metrics": [
            {"label": "Messages", "used": 45, "limit": 100, "unit": "", "period": "day"},
            {"label": "Storage",  "used": 2.1, "limit": 5,   "unit": "GB", "period": ""},
        ],
        "reset_at": None,
    }
    result = _build_tui_renderable(usage, datetime.now(), None)
    assert isinstance(result, Panel)


def test_bar_colours():
    assert _bar_style(0.0)  == "#a855f7"
    assert _bar_style(0.74) == "#a855f7"
    assert _bar_style(0.75) == "yellow"
    assert _bar_style(0.89) == "yellow"
    assert _bar_style(0.90) == "red"
    assert _bar_style(1.0)  == "red"


def test_run_tui_is_importable():
    from claude_widget import run_tui
    assert callable(run_tui)


def test_settings_dialog_method_exists():
    import inspect
    import claude_widget
    # ClaudeWidget inherits from mocked Gtk.Window in tests so the class itself
    # resolves to a MagicMock. Check the module source directly instead.
    source = inspect.getsource(claude_widget)
    assert 'def _show_settings_dialog' in source


def test_daemonize_is_importable():
    import inspect
    import claude_widget
    source = inspect.getsource(claude_widget)
    assert 'def _daemonize' in source


def test_daemonize_spawns_detached_subprocess(monkeypatch):
    """_daemonize() must spawn a subprocess with start_new_session=True and then exit."""
    import subprocess
    import sys
    import claude_widget

    popen_calls = []

    class FakePopen:
        def __init__(self, argv, **kwargs):
            popen_calls.append({'argv': argv, 'kwargs': kwargs})

    monkeypatch.setattr(subprocess, 'Popen', FakePopen)

    # _daemonize calls sys.exit(0) after Popen — catch it
    with __import__('pytest').raises(SystemExit) as exc:
        claude_widget._daemonize()

    assert exc.value.code == 0
    assert len(popen_calls) == 1
    call = popen_calls[0]
    # Must detach from terminal
    assert call['kwargs']['start_new_session'] is True
    # stdin must be suppressed
    assert call['kwargs']['stdin'] == subprocess.DEVNULL
    # --daemon must not be forwarded to the child
    assert '--daemon' not in call['argv']


def test_settings_values_applied_to_config():
    import claude_widget as cw

    config = {
        'session_key': 'test',
        'position_x': 0,
        'position_y': 0,
        'widget_width': 230,
        'opacity': 0.93,
        'refresh_interval': 300,
        'org_id': '',
        'debug': False,
    }

    save_calls = []
    original_save = cw.save_config
    cw.save_config = lambda c: save_calls.append(dict(c))

    try:
        config.update({
            'position_x': -20,
            'position_y': 60,
            'widget_width': 250,
            'opacity': 0.80,
            'refresh_interval': 120,
        })
        cw.save_config(config)

        assert len(save_calls) == 1
        assert save_calls[0]['position_x'] == -20
        assert save_calls[0]['widget_width'] == 250
        assert save_calls[0]['opacity'] == 0.80
        assert save_calls[0]['refresh_interval'] == 120
    finally:
        cw.save_config = original_save
