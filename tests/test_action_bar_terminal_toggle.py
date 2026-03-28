"""Tests for the ActionBar terminal toggle button (task-10-action-bar).

Verifies the structure and content of actions.js to ensure:
  1. terminalOpen and onToggleTerminal are in the ActionBar function signature
  2. Terminal toggle button exists with proper title attribute (keyboard shortcut hint)
  3. The button uses dynamic icon: ph-terminal-window-fill when open, ph-terminal-window when closed
  4. The terminal button appears BEFORE the Upload button in the normal toolbar
  5. The button's onClick is wired to onToggleTerminal

Tests follow the static-analysis approach used throughout this project —
inspecting the JS source text rather than running a JS test framework.
"""

import re
from functools import lru_cache
from pathlib import Path

ACTIONS_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "actions.js"
)


@lru_cache(maxsize=1)
def read_actions() -> str:
    return ACTIONS_FILE.read_text()


# ── TestFileExists ────────────────────────────────────────────────────────────


class TestFileExists:
    def test_actions_file_exists(self):
        """The component file must exist at the expected path."""
        assert ACTIONS_FILE.exists(), f"actions.js not found at {ACTIONS_FILE}"


# ── TestFunctionSignature ─────────────────────────────────────────────────────


class TestFunctionSignature:
    def test_function_signature_includes_terminal_open(self):
        """ActionBar function signature must include terminalOpen prop."""
        src = read_actions()
        assert re.search(
            r"function\s+ActionBar\s*\(\s*\{[^}]*terminalOpen[^}]*\}", src
        ), (
            "terminalOpen not found in ActionBar function signature — "
            "must be destructured in the parameter list"
        )

    def test_function_signature_includes_on_toggle_terminal(self):
        """ActionBar function signature must include onToggleTerminal prop."""
        src = read_actions()
        assert re.search(
            r"function\s+ActionBar\s*\(\s*\{[^}]*onToggleTerminal[^}]*\}", src
        ), (
            "onToggleTerminal not found in ActionBar function signature — "
            "must be destructured in the parameter list"
        )


# ── TestTerminalButton ────────────────────────────────────────────────────────


class TestTerminalButton:
    def test_terminal_button_has_on_toggle_terminal_handler(self):
        """Terminal button onClick must be wired to onToggleTerminal."""
        src = read_actions()
        assert "onClick=${onToggleTerminal}" in src or "onClick={onToggleTerminal}" in src, (
            "Terminal button not wired to onToggleTerminal handler"
        )

    def test_terminal_button_has_keyboard_shortcut_in_title(self):
        """Terminal button title must include keyboard shortcut hint Ctrl+`."""
        src = read_actions()
        # The title should be "Toggle terminal (Ctrl+`)"
        assert "Toggle terminal (Ctrl+" in src, (
            "Terminal button title does not contain keyboard shortcut hint 'Toggle terminal (Ctrl+`)"
        )

    def test_terminal_button_has_terminal_text(self):
        """Terminal button must have 'Terminal' label text."""
        src = read_actions()
        assert " Terminal</button>" in src or "> Terminal</button>" in src or "Terminal</button>" in src, (
            "Terminal button text not found — button must contain 'Terminal' label"
        )

    def test_terminal_button_has_filled_icon_when_open(self):
        """Terminal button must use ph-terminal-window-fill icon when terminalOpen is true."""
        src = read_actions()
        assert "ph-terminal-window-fill" in src, (
            "ph-terminal-window-fill icon not found — "
            "the icon must be filled (ph-terminal-window-fill) when terminalOpen is true"
        )

    def test_terminal_button_icon_is_dynamic_based_on_terminal_open(self):
        """Terminal button icon must toggle between ph-terminal-window-fill and ph-terminal-window."""
        src = read_actions()
        # Must have a ternary expression with terminalOpen that switches between icons
        assert re.search(
            r"terminalOpen\s*\?\s*['\"]ph-terminal-window-fill['\"]\s*:\s*['\"]ph-terminal-window['\"]",
            src,
        ), (
            "Dynamic icon based on terminalOpen not found — "
            "must use: terminalOpen ? 'ph-terminal-window-fill' : 'ph-terminal-window'"
        )

    def test_terminal_button_before_upload_button_in_normal_toolbar(self):
        """Terminal toggle button must appear BEFORE the Upload button in the normal toolbar.

        The spec says: add terminal button 'BEFORE the Upload button' — so the
        Terminal button must come first in the action bar.
        """
        src = read_actions()
        # Find the normal toolbar section (after the batch toolbar return)
        # Look for the second action-bar div (normal toolbar)
        # The terminal button (onToggleTerminal) must appear before the Upload button (onShowUpload)
        toggle_pos = src.rfind("onToggleTerminal")
        upload_pos = src.rfind("onShowUpload")
        assert toggle_pos != -1, "onToggleTerminal not found in normal toolbar"
        assert upload_pos != -1, "onShowUpload not found in normal toolbar"
        assert toggle_pos < upload_pos, (
            f"Terminal button (onToggleTerminal at pos {toggle_pos}) appears AFTER "
            f"Upload button (onShowUpload at pos {upload_pos}) — "
            "spec requires terminal button to be BEFORE the Upload button"
        )
