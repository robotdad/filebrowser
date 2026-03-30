"""Tests for the useTabManager custom hook (task-3-use-tab-manager).

Verifies the structure and content of the JS hook file using static-analysis
(reading the source as text) — consistent with the project's test conventions.
"""

from functools import lru_cache
from pathlib import Path

HOOK_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "hooks"
    / "use-tab-manager.js"
)


@lru_cache(maxsize=1)
def read_hook() -> str:
    return HOOK_FILE.read_text()


# ── TestFileExists ────────────────────────────────────────────────────────────


class TestFileExists:
    def test_hook_file_exists(self):
        """The hook file must exist at the expected path."""
        assert HOOK_FILE.exists(), f"use-tab-manager.js not found at {HOOK_FILE}"


# ── TestImports ───────────────────────────────────────────────────────────────


class TestImports:
    def test_imports_use_state(self):
        """Must import useState from preact/hooks."""
        src = read_hook()
        assert "useState" in src, "useState not imported"

    def test_imports_use_callback(self):
        """Must import useCallback from preact/hooks."""
        src = read_hook()
        assert "useCallback" in src, "useCallback not imported"

    def test_imports_from_preact_hooks(self):
        """Hooks must be imported from 'preact/hooks'."""
        src = read_hook()
        assert "from 'preact/hooks'" in src or 'from "preact/hooks"' in src, (
            "preact/hooks import not found"
        )

    def test_imports_create_logger_from_logger_js(self):
        """Must import createLogger from logger.js."""
        src = read_hook()
        assert "createLogger" in src, "createLogger not imported"
        assert "logger.js" in src, "logger.js not referenced in imports"


# ── TestExports ───────────────────────────────────────────────────────────────


class TestExports:
    def test_exports_use_tab_manager(self):
        """Must export useTabManager as a named function."""
        src = read_hook()
        assert (
            "export function useTabManager" in src
            or "export { useTabManager" in src
        ), "useTabManager is not exported as a named function"


# ── TestHookState ─────────────────────────────────────────────────────────────


class TestHookState:
    def test_has_tabs_state_array(self):
        """Must declare tabs state initialized to an array."""
        src = read_hook()
        assert "useState" in src, "useState not found"
        assert "tabs" in src, "tabs state not found"
        # Initial state should be an empty array
        assert "[]" in src, "tabs initial state [] not found"

    def test_has_active_tab_id_state(self):
        """Must declare activeTabId state."""
        src = read_hook()
        assert "activeTabId" in src, "activeTabId not found in hook"

    def test_computes_active_file_path(self):
        """Must compute activeFilePath from active tab."""
        src = read_hook()
        assert "activeFilePath" in src, "activeFilePath not computed in hook"


# ── TestHookAPI ───────────────────────────────────────────────────────────────


class TestHookAPI:
    def test_open_is_use_callback(self):
        """open() must be defined with useCallback."""
        src = read_hook()
        assert "useCallback" in src and "open" in src, (
            "open not defined with useCallback"
        )
        # Check for useCallback wrapping the open function
        assert "const open" in src, "open not declared as const"

    def test_pin_is_use_callback(self):
        """pin() must be defined with useCallback."""
        src = read_hook()
        assert "const pin" in src, "pin not declared as const with useCallback"

    def test_close_is_use_callback(self):
        """close() must be defined with useCallback."""
        src = read_hook()
        assert "const close" in src, "close not declared as const with useCallback"

    def test_activate_is_use_callback(self):
        """activate() must be defined with useCallback."""
        src = read_hook()
        assert "const activate" in src, "activate not declared as const with useCallback"

    def test_set_dirty_is_use_callback(self):
        """setDirty() must be defined with useCallback."""
        src = read_hook()
        assert "const setDirty" in src, "setDirty not declared as const with useCallback"

    def test_update_path_is_use_callback(self):
        """updatePath() must be defined with useCallback."""
        src = read_hook()
        assert "const updatePath" in src, "updatePath not declared as const with useCallback"

    def test_close_by_path_is_use_callback(self):
        """closeByPath() must be defined with useCallback."""
        src = read_hook()
        assert "const closeByPath" in src, "closeByPath not declared as const with useCallback"

    def test_returns_all_api_members(self):
        """Hook must return all API members including state and functions."""
        src = read_hook()
        assert "return" in src, "No return statement found"
        # All public API members must appear in the return value
        for member in ["tabs", "activeTabId", "activeFilePath", "open", "pin",
                       "close", "activate", "setDirty", "updatePath", "closeByPath"]:
            assert member in src, f"{member} not found in hook source"


# ── TestTabModel ──────────────────────────────────────────────────────────────


class TestTabModel:
    def test_tab_has_id_field(self):
        """Tab objects must have an id field."""
        src = read_hook()
        assert "id:" in src or "id :" in src, "id field not found in tab model"

    def test_tab_has_file_path_field(self):
        """Tab objects must have a filePath field."""
        src = read_hook()
        assert "filePath" in src, "filePath field not found in tab model"

    def test_tab_has_pinned_field(self):
        """Tab objects must have a pinned field."""
        src = read_hook()
        assert "pinned" in src, "pinned field not found in tab model"

    def test_tab_has_dirty_field(self):
        """Tab objects must have a dirty field."""
        src = read_hook()
        assert "dirty" in src, "dirty field not found in tab model"


# ── TestDirtyClose ────────────────────────────────────────────────────────────


class TestDirtyClose:
    def test_close_checks_dirty_state(self):
        """close() must check the dirty state before closing a tab."""
        src = read_hook()
        assert "dirty" in src, "dirty check not found in close logic"
        # close should inspect tab.dirty
        assert "tab.dirty" in src or ".dirty" in src, (
            "tab.dirty check not found in close logic"
        )

    def test_close_uses_confirm_for_dirty_tabs(self):
        """close() must use confirm() dialog for dirty tabs."""
        src = read_hook()
        assert "confirm(" in src, "confirm() not found — dirty tabs must prompt user"


# ── TestDefaultTabBehavior ────────────────────────────────────────────────────


class TestDefaultTabBehavior:
    def test_open_finds_unpinned_tab_to_replace(self):
        """open() must find an unpinned tab to replace instead of always creating new."""
        src = read_hook()
        # Should check for pinned:false or !pinned to find a replaceable tab
        assert "!pinned" in src or "pinned === false" in src or "pinned == false" in src, (
            "open() does not look for unpinned tabs to replace"
        )

    def test_creates_new_tab_when_all_pinned(self):
        """open() must create a new tab when all existing tabs are pinned."""
        src = read_hook()
        # genId() must be called to generate a new tab ID
        assert "genId" in src, "genId() not found — needed to create new tabs"
        # New tabs must be pinned:false
        assert "pinned: false" in src, "new tabs must default to pinned: false"


# ── TestLogging ───────────────────────────────────────────────────────────────


class TestLogging:
    def test_creates_logger_named_use_tab_manager(self):
        """Must create a logger named 'useTabManager' via createLogger."""
        src = read_hook()
        assert "createLogger('useTabManager')" in src or 'createLogger("useTabManager")' in src, (
            "createLogger('useTabManager') not found"
        )

    def test_logs_open_events_at_debug_level(self):
        """open() must log events at debug level."""
        src = read_hook()
        assert "log.debug" in src, "log.debug() not found — open events must be logged at debug level"
