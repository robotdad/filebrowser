"""Tests for the ContextMenu component changes (task-9-context-menu).

Verifies the structure and content of context-menu.js to ensure:
  1. onOpenTerminal is in the function signature
  2. 'Open Terminal Here' button appears for directories, with ph-terminal-window icon
  3. A divider follows the terminal menu item
  4. The menu height estimate is 220 for directories
  5. The button is conditionally rendered only for directories with onOpenTerminal set

Tests follow the static-analysis approach used throughout this project —
inspecting the JS source text rather than running a JS test framework.
"""

import re
from functools import lru_cache
from pathlib import Path

CONTEXT_MENU_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "context-menu.js"
)


@lru_cache(maxsize=1)
def read_context_menu() -> str:
    return CONTEXT_MENU_FILE.read_text()


# ── TestFileExists ─────────────────────────────────────────────────────────────


class TestFileExists:
    def test_context_menu_file_exists(self):
        """The component file must exist at the expected path."""
        assert CONTEXT_MENU_FILE.exists(), (
            f"context-menu.js not found at {CONTEXT_MENU_FILE}"
        )


# ── TestFunctionSignature ──────────────────────────────────────────────────────


class TestFunctionSignature:
    def test_function_signature_includes_on_open_terminal(self):
        """ContextMenu function signature must include onOpenTerminal prop."""
        src = read_context_menu()
        assert re.search(
            r"function\s+ContextMenu\s*\(\s*\{[^}]*onOpenTerminal[^}]*\}", src
        ), (
            "onOpenTerminal not found in ContextMenu function signature — "
            "must be destructured in the parameter list"
        )

    def test_function_exports_context_menu(self):
        """ContextMenu must be exported."""
        src = read_context_menu()
        assert "export function ContextMenu" in src, (
            "ContextMenu is not exported"
        )


# ── TestTerminalMenuItem ───────────────────────────────────────────────────────


class TestTerminalMenuItem:
    def test_open_terminal_here_button_text(self):
        """Button text must be exactly 'Open Terminal Here' (spec requirement)."""
        src = read_context_menu()
        assert "Open Terminal Here" in src, (
            "'Open Terminal Here' button text not found in context-menu.js — "
            "the spec requires this exact label"
        )

    def test_terminal_menu_item_has_ph_terminal_window_icon(self):
        """Terminal menu item must use ph-terminal-window icon."""
        src = read_context_menu()
        assert "ph-terminal-window" in src, (
            "ph-terminal-window icon not found in context-menu.js"
        )

    def test_terminal_menu_item_uses_on_open_terminal_handler(self):
        """Terminal menu item onClick must be wired to act(onOpenTerminal)."""
        src = read_context_menu()
        # The button must reference onOpenTerminal
        assert re.search(r"act\s*\(\s*onOpenTerminal\s*\)", src), (
            "act(onOpenTerminal) not found — terminal button must use the act() wrapper"
        )

    def test_divider_follows_terminal_menu_item(self):
        """A context-menu-divider must appear after the terminal button."""
        src = read_context_menu()
        # Check that both the terminal button and a divider are present together
        assert "ph-terminal-window" in src, "ph-terminal-window icon not found"
        # Find position of the terminal button and a divider after it
        terminal_pos = src.find("ph-terminal-window")
        divider_pos = src.find("context-menu-divider", terminal_pos)
        assert divider_pos != -1, (
            "No context-menu-divider found after the terminal menu item — "
            "a divider must follow the 'Open Terminal Here' button"
        )

    def test_terminal_item_only_for_directories(self):
        """Terminal menu item must be conditionally rendered for directories only."""
        src = read_context_menu()
        # Find the section that renders the terminal button
        # It should be guarded by menu.type === 'directory'
        # Look for the pattern: directory && onOpenTerminal
        assert re.search(
            r"menu\.type\s*===\s*['\"]directory['\"]\s*&&\s*onOpenTerminal", src
        ), (
            "Terminal menu item not guarded by 'menu.type === directory && onOpenTerminal' — "
            "it must only appear for directories when onOpenTerminal is provided"
        )

    def test_terminal_item_has_context_menu_item_class(self):
        """Terminal menu button must have context-menu-item class."""
        src = read_context_menu()
        # Find the terminal button and verify its class
        # The button containing ph-terminal-window must have context-menu-item
        terminal_idx = src.find("ph-terminal-window")
        assert terminal_idx != -1, "ph-terminal-window not found"
        # Look backwards from terminal icon for the button opening tag
        preceding_text = src[max(0, terminal_idx - 200):terminal_idx]
        assert "context-menu-item" in preceding_text, (
            "Terminal button does not have 'context-menu-item' class — "
            "class must be set on the button element before the icon"
        )


# ── TestMenuHeight ─────────────────────────────────────────────────────────────


class TestMenuHeight:
    def test_menu_height_file_type_is_200(self):
        """menuH for file type must be 200."""
        src = read_context_menu()
        # Should have: menu.type === 'file' ? 200 : ...
        assert re.search(
            r"menu\.type\s*===\s*['\"]file['\"]\s*\?\s*200", src
        ), "menuH for file type (200) not found"

    def test_menu_height_directory_type_is_220(self):
        """menuH for directory type must be 220 (not 160)."""
        src = read_context_menu()
        # Should have: ... ? 200 : 220
        assert re.search(
            r"menu\.type\s*===\s*['\"]file['\"]\s*\?\s*200\s*:\s*220", src
        ), (
            "menuH for directory type is not 220 — spec requires "
            "'menu.type === 'file' ? 200 : 220'"
        )

    def test_menu_height_not_160_for_directory(self):
        """menuH must NOT use 160 for directory type (old incorrect value)."""
        src = read_context_menu()
        # Ensure the old value (160) is not used in menuH
        assert not re.search(
            r"menu\.type\s*===\s*['\"]file['\"]\s*\?\s*200\s*:\s*160", src
        ), (
            "menuH still uses 160 for directory — must be updated to 220 "
            "to account for the new 'Open Terminal Here' menu item"
        )
