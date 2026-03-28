"""Tests for the TerminalPanel Preact component (task-6-terminal-preact-component).

Verifies the structure and content of the JS component file rather than
running a JS test framework — consistent with how test_index_html.py tests
the static frontend assets.
"""

import re
from functools import lru_cache
from pathlib import Path

COMPONENT_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "terminal.js"
)


@lru_cache(maxsize=1)
def read_component() -> str:
    return COMPONENT_FILE.read_text()


# ── TestFileExists ──────────────────────────────────────────────────────────


class TestFileExists:
    def test_terminal_component_file_exists(self):
        """The component file must exist at the expected path."""
        assert COMPONENT_FILE.exists(), f"terminal.js not found at {COMPONENT_FILE}"


# ── TestImports ─────────────────────────────────────────────────────────────


class TestImports:
    def test_imports_use_effect(self):
        """Must import useEffect from preact/hooks."""
        src = read_component()
        assert "useEffect" in src, "useEffect not imported"

    def test_imports_use_ref(self):
        """Must import useRef from preact/hooks."""
        src = read_component()
        assert "useRef" in src, "useRef not imported"

    def test_imports_use_callback(self):
        """Must import useCallback from preact/hooks."""
        src = read_component()
        assert "useCallback" in src, "useCallback not imported"

    def test_imports_from_preact_hooks(self):
        """Hooks must be imported from 'preact/hooks'."""
        src = read_component()
        assert "from 'preact/hooks'" in src or 'from "preact/hooks"' in src, (
            "preact/hooks import not found"
        )

    def test_imports_html_from_html_js(self):
        """Must import html from '../html.js'."""
        src = read_component()
        assert "../html.js" in src, "html.js import not found"

    def test_imports_terminal_from_xterm(self):
        """Must import Terminal from '@xterm/xterm'."""
        src = read_component()
        assert "@xterm/xterm" in src, "@xterm/xterm import not found"
        assert "Terminal" in src, "Terminal not imported from @xterm/xterm"

    def test_imports_fit_addon_from_xterm(self):
        """Must import FitAddon from '@xterm/addon-fit'."""
        src = read_component()
        assert "@xterm/addon-fit" in src, "@xterm/addon-fit import not found"
        assert "FitAddon" in src, "FitAddon not imported from @xterm/addon-fit"


# ── TestExports ─────────────────────────────────────────────────────────────


class TestExports:
    def test_exports_terminal_panel(self):
        """Component must export TerminalPanel."""
        src = read_component()
        assert (
            "export function TerminalPanel" in src or "export { TerminalPanel" in src
        ), "TerminalPanel is not exported"


# ── TestProps ───────────────────────────────────────────────────────────────


class TestProps:
    def test_accepts_cwd_prop(self):
        """Component must accept a cwd prop."""
        src = read_component()
        assert "cwd" in src, "cwd prop not referenced in component"

    def test_accepts_on_close_prop(self):
        """Component must accept an onClose prop."""
        src = read_component()
        assert "onClose" in src, "onClose prop not referenced in component"

    def test_accepts_dock_position_prop(self):
        """Component must accept a dockPosition prop."""
        src = read_component()
        assert "dockPosition" in src, "dockPosition prop not referenced in component"

    def test_accepts_on_toggle_dock_prop(self):
        """Component must accept an onToggleDock prop."""
        src = read_component()
        assert "onToggleDock" in src, "onToggleDock prop not referenced in component"


# ── TestRefs ────────────────────────────────────────────────────────────────


class TestRefs:
    def test_uses_container_ref(self):
        """Must declare containerRef."""
        src = read_component()
        assert "containerRef" in src, "containerRef not found"

    def test_does_not_keep_redundant_term_ref(self):
        """Unused terminal refs should be removed instead of stored as dead state."""
        src = read_component()
        assert "const termRef" not in src, "Unused termRef should not be declared"

    def test_does_not_keep_redundant_ws_ref(self):
        """Unused websocket refs should be removed instead of stored as dead state."""
        src = read_component()
        assert "const wsRef" not in src, "Unused wsRef should not be declared"

    def test_no_stray_wsref_current_assignment(self):
        """wsRef.current = ws must not appear — wsRef is never declared.

        Using an undeclared wsRef causes a ReferenceError at runtime when
        TerminalPanel mounts or when cwd changes.  The ws local variable
        is already in scope for the effect closure; storing it in a ref
        that nobody reads serves no purpose and crashes the component.
        """
        src = read_component()
        assert "wsRef.current" not in src, (
            "wsRef.current found in terminal.js — wsRef is never declared, "
            "this assignment throws ReferenceError at runtime.  "
            "Remove it; the effect closure already captures 'ws' directly."
        )

    def test_uses_fit_ref(self):
        """Must declare fitRef."""
        src = read_component()
        assert "fitRef" in src, "fitRef not found"


# ── TestTerminalConfig ───────────────────────────────────────────────────────


class TestTerminalConfig:
    def test_cursor_blink_enabled(self):
        """Terminal must be created with cursorBlink: true."""
        src = read_component()
        assert "cursorBlink" in src and "true" in src, (
            "cursorBlink: true not found in terminal config"
        )

    def test_font_size_13(self):
        """Terminal must use fontSize: 13."""
        src = read_component()
        assert "fontSize" in src and "13" in src, (
            "fontSize: 13 not found in terminal config"
        )

    def test_font_family_jetbrains_mono(self):
        """Terminal must include 'JetBrains Mono' in font family."""
        src = read_component()
        assert "JetBrains Mono" in src, "JetBrains Mono not found in fontFamily config"

    def test_dark_theme_background(self):
        """Terminal dark theme must use background #1c1c1e."""
        src = read_component()
        assert "#1c1c1e" in src, "Dark theme background #1c1c1e not found"

    def test_dark_theme_foreground(self):
        """Terminal dark theme must use foreground #f5f5f7."""
        src = read_component()
        assert "#f5f5f7" in src, "Dark theme foreground #f5f5f7 not found"


# ── TestWebSocket ────────────────────────────────────────────────────────────


class TestWebSocket:
    def test_websocket_url_uses_api_terminal(self):
        """WebSocket must connect to /api/terminal."""
        src = read_component()
        assert "/api/terminal" in src, "/api/terminal not found in WebSocket URL"

    def test_websocket_url_uses_path_param(self):
        """WebSocket URL must include path query parameter with encoded cwd."""
        src = read_component()
        assert "path=" in src and "encodeURIComponent" in src, (
            "path query param with encodeURIComponent not found"
        )

    def test_websocket_uses_protocol(self):
        """WebSocket must use protocol variable for ws:// or wss://."""
        src = read_component()
        # Should derive protocol from window.location.protocol
        assert "location.protocol" in src or "location.host" in src, (
            "WebSocket URL must use window location for protocol/host"
        )

    def test_websocket_sends_resize_on_connect(self):
        """On WebSocket open: must send initial resize dimensions."""
        src = read_component()
        # All of these must be present and wired together — not just one of them
        assert "onopen" in src, "WebSocket onopen handler not found"
        assert "ws.send" in src, "ws.send() call not found in onopen handler"
        assert '"resize"' in src or "'resize'" in src, (
            "resize type not found in initial send payload"
        )
        assert "cols" in src and "rows" in src, (
            "cols/rows not found in initial resize payload"
        )


# ── TestEventHandlers ─────────────────────────────────────────────────────


class TestEventHandlers:
    def test_on_message_writes_to_terminal(self):
        """WebSocket onmessage must write to terminal."""
        src = read_component()
        assert "onmessage" in src, "WebSocket onmessage handler not found"
        assert ".write(" in src, "terminal.write() call not found"

    def test_on_close_writes_session_ended(self):
        """WebSocket onclose must write session-ended message."""
        src = read_component()
        assert "Terminal session ended" in src, (
            "[Terminal session ended] message not found in onclose handler"
        )

    def test_on_error_writes_connection_error(self):
        """WebSocket onerror must write connection error message."""
        src = read_component()
        assert "Connection error" in src, (
            "[Connection error] message not found in onerror handler"
        )

    def test_on_data_sends_to_websocket(self):
        """Terminal onData must send data to WebSocket."""
        src = read_component()
        assert "onData" in src, "onData handler not found"
        assert "ws.send" in src, (
            "ws.send() not found — onData must forward input to WebSocket"
        )

    def test_on_resize_sends_json_resize_message(self):
        """Terminal onResize must send JSON resize message."""
        src = read_component()
        assert "onResize" in src, "onResize handler not found"
        assert "JSON.stringify" in src, "JSON.stringify not found in resize message"
        assert "cols" in src and "rows" in src, (
            "cols/rows fields not found in resize payload"
        )


# ── TestResizeHandling ────────────────────────────────────────────────────


class TestResizeHandling:
    def test_resize_observer_coalesces_fit_with_schedule_helper(self):
        """Resize handling must funnel through one shared rAF-coalesced helper."""
        src = read_component()
        assert "const scheduleFit = useCallback(() => {" in src, (
            "Missing shared scheduleFit helper for all fit requests"
        )
        assert "if (fitFrameRef.current !== null) return;" in src, (
            "scheduleFit must coalesce repeat resize work behind one pending frame"
        )
        assert "fitFrameRef.current = requestAnimationFrame(() => {" in src, (
            "scheduleFit must queue fit work in requestAnimationFrame"
        )

    def test_resize_handling_uses_resize_observer_without_window_listener(self):
        """ResizeObserver should be the only resize signal source."""
        src = read_component()
        assert (
            "ResizeObserver(() => scheduleFit())" in src
            or "new ResizeObserver(scheduleFit)" in src
        ), "ResizeObserver must delegate to scheduleFit"
        assert "addEventListener('resize'" not in src, (
            "window resize listener duplicates ResizeObserver work"
        )
        assert "removeEventListener('resize'" not in src, (
            "cleanup should not need a removed window resize listener"
        )

    def test_dock_toggle_relies_on_resize_observer(self):
        """Dock toggles should not need a second useEffect just to fit."""
        src = read_component()
        assert not re.search(
            r"useEffect\(\(\)\s*=>\s*\{[\s\S]*?\},\s*\[dockPosition\]\);", src
        ), "dockPosition refit should be handled by ResizeObserver, not a second effect"


# ── TestCleanup ───────────────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_disconnects_observer(self):
        """Cleanup must disconnect the ResizeObserver."""
        src = read_component()
        assert ".disconnect()" in src, (
            "ResizeObserver .disconnect() not found in cleanup"
        )

    def test_cleanup_cancels_pending_fit_frame(self):
        """Cleanup must cancel any queued fit frame before tearing down."""
        src = read_component()
        assert "cancelAnimationFrame(fitFrameRef.current)" in src, (
            "cleanup must cancel any queued fit animation frame"
        )

    def test_cleanup_closes_websocket(self):
        """Cleanup must close the WebSocket."""
        src = read_component()
        assert ".close()" in src, "WebSocket .close() not found in cleanup"

    def test_cleanup_disposes_terminal(self):
        """Cleanup must dispose the terminal."""
        src = read_component()
        assert ".dispose()" in src, "terminal .dispose() not found in cleanup"

    def test_cleanup_suppresses_ws_callbacks(self):
        """Cleanup must null out WebSocket callbacks before closing.

        Without this, ws.close() triggers ws.onclose which writes
        '[Terminal session ended]' to a terminal that may already be disposed
        (teardown race on cwd changes / unmounts).

        NOTE: This is a presence-check baseline. See TestWebSocketTeardownRace
        for stronger ordering and completeness assertions.
        """
        src = read_component()
        # All four WS callback slots must be explicitly cleared.
        # Use regex to tolerate alignment whitespace (e.g. ``ws.onopen    = null``).
        for attr in ("ws.onopen", "ws.onmessage", "ws.onclose", "ws.onerror"):
            assert re.search(rf"{re.escape(attr)}\s+=\s+null", src), (
                f"{attr} not cleared in cleanup — "
                "must null out WebSocket callbacks before ws.close() "
                "to prevent stale callbacks writing to a disposed terminal"
            )


# ── TestWebSocketTeardownRace ────────────────────────────────────────────────
#
# Regression suite for the async teardown race:
#   When cwd changes (or the component unmounts), React/Preact runs the cleanup
#   returned by the main useEffect.  Without nulling callbacks first, ws.close()
#   fires ws.onclose → term.write('[Terminal session ended]') on an already-
#   disposed Terminal instance, causing "Cannot read properties of undefined"
#   errors and potential memory leaks.
#
# These tests inspect the *source* ordering, which is the only surface available
# without a full JS runtime.  They verify:
#   1. Every callback slot is cleared (not just any-one-of-four).
#   2. Every null-assignment appears *before* ws.close() in the source.
#   3. ws.close() appears before term.dispose() (correct teardown sequence).
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSocketTeardownRace:
    """Source-ordering regression tests for the WebSocket teardown race.

    The fix (terminal.js lines 117-121) nulls all four callback slots before
    calling ws.close().  These tests verify that fix cannot be silently broken
    by a future refactor that reorders or omits the null assignments.
    """

    # -- helpers ----------------------------------------------------------------

    @staticmethod
    def _cleanup_block(src: str) -> str:
        """Return the text of the ``return () => { ... }`` cleanup closure."""
        marker = "return () => {"
        start = src.find(marker)
        if start == -1:
            return src
        depth = 0
        for i, ch in enumerate(src[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return src[start : i + 1]
        return src[start:]

    # -- helpers for regex-based position search --------------------------------

    @staticmethod
    def _find_pos(src: str, attr: str) -> int:
        """Return the start position of ``attr = null`` in *src*, or -1.

        Uses a regex that tolerates alignment whitespace, e.g.
        ``ws.onopen    = null`` matches the same as ``ws.onopen = null``.
        """
        m = re.search(rf"{re.escape(attr)}\s+=\s+null", src)
        return m.start() if m else -1

    # -- completeness -----------------------------------------------------------

    def test_all_four_ws_callbacks_cleared_in_cleanup(self):
        """Every WebSocket callback slot must be set to null in cleanup.

        Clearing only ws.onclose / ws.onerror is insufficient: a rapid
        cwd change can still deliver an onmessage/onopen after the new
        terminal instance is created.  All four must be cleared.
        """
        cleanup = self._cleanup_block(read_component())
        for attr in ("ws.onopen", "ws.onmessage", "ws.onclose", "ws.onerror"):
            assert re.search(rf"{re.escape(attr)}\s+=\s+null", cleanup), (
                f"{attr} = null not found inside the cleanup closure — "
                "all four WebSocket callbacks must be cleared before ws.close()"
            )

    # -- ordering: null-assignments come before ws.close() ---------------------

    def test_onclose_cleared_before_ws_close(self):
        """ws.onclose must be nulled *before* ws.close() is called.

        ws.close() triggers the browser to fire the onclose event synchronously
        (when the socket is already CLOSING/CLOSED) or asynchronously.  Either
        way, if onclose is not null the handler runs and calls term.write() on
        an already-disposed Terminal, crashing the app.
        """
        src = read_component()
        null_pos = self._find_pos(src, "ws.onclose")
        close_pos = src.find("ws.close()")
        assert null_pos != -1, "ws.onclose = null not found"
        assert close_pos != -1, "ws.close() not found"
        assert null_pos < close_pos, (
            f"ws.onclose = null (pos {null_pos}) appears AFTER "
            f"ws.close() (pos {close_pos}) — must be before"
        )

    def test_onerror_cleared_before_ws_close(self):
        """ws.onerror must be nulled *before* ws.close() is called.

        A socket close can also raise an error event.  If onerror is still
        wired it calls term.write('[Connection error]') on a disposed terminal.
        """
        src = read_component()
        null_pos = self._find_pos(src, "ws.onerror")
        close_pos = src.find("ws.close()")
        assert null_pos != -1, "ws.onerror = null not found"
        assert close_pos != -1, "ws.close() not found"
        assert null_pos < close_pos, (
            f"ws.onerror = null (pos {null_pos}) appears AFTER "
            f"ws.close() (pos {close_pos}) — must be before"
        )

    def test_onopen_cleared_before_ws_close(self):
        """ws.onopen must be nulled *before* ws.close() is called."""
        src = read_component()
        null_pos = self._find_pos(src, "ws.onopen")
        close_pos = src.find("ws.close()")
        assert null_pos != -1, "ws.onopen = null not found"
        assert close_pos != -1, "ws.close() not found"
        assert null_pos < close_pos, (
            f"ws.onopen = null (pos {null_pos}) appears AFTER "
            f"ws.close() (pos {close_pos}) — must be before"
        )

    def test_onmessage_cleared_before_ws_close(self):
        """ws.onmessage must be nulled *before* ws.close() is called."""
        src = read_component()
        null_pos = self._find_pos(src, "ws.onmessage")
        close_pos = src.find("ws.close()")
        assert null_pos != -1, "ws.onmessage = null not found"
        assert close_pos != -1, "ws.close() not found"
        assert null_pos < close_pos, (
            f"ws.onmessage = null (pos {null_pos}) appears AFTER "
            f"ws.close() (pos {close_pos}) — must be before"
        )

    # -- full teardown sequence -------------------------------------------------

    def test_ws_close_before_term_dispose(self):
        """ws.close() must be called *before* term.dispose().

        This is the correct teardown order: stop I/O first, then free the
        rendering surface.  Disposing the terminal before closing the socket
        can still deliver messages to a dead xterm.js instance.
        """
        src = read_component()
        close_pos = src.find("ws.close()")
        dispose_pos = src.find("term.dispose()")
        assert close_pos != -1, "ws.close() not found"
        assert dispose_pos != -1, "term.dispose() not found"
        assert close_pos < dispose_pos, (
            f"ws.close() (pos {close_pos}) appears AFTER "
            f"term.dispose() (pos {dispose_pos}) — socket must be closed first"
        )


# ── TestRender ───────────────────────────────────────────────────────────


class TestRender:
    def test_renders_terminal_panel_class(self):
        """Must render element with terminal-panel class."""
        src = read_component()
        assert "terminal-panel" in src, ".terminal-panel class not found in render"

    def test_renders_terminal_container_class(self):
        """Must render element with terminal-container class."""
        src = read_component()
        assert "terminal-container" in src, (
            ".terminal-container class not found in render"
        )

    def test_renders_header_with_terminal_icon(self):
        """Header must contain ph-terminal-window icon."""
        src = read_component()
        assert "ph-terminal-window" in src, "ph-terminal-window icon not found"

    def test_renders_dock_toggle_button(self):
        """Must render dock toggle button with ph-rows/ph-columns icon."""
        src = read_component()
        assert "ph-rows" in src or "ph-columns" in src, (
            "ph-rows/ph-columns icon not found in dock toggle button"
        )

    def test_renders_close_button(self):
        """Must render close button with ph-x icon."""
        src = read_component()
        assert "ph-x" in src, "ph-x icon not found in close button"

    def test_container_ref_on_terminal_container(self):
        """containerRef must be attached to the terminal-container div."""
        src = read_component()
        assert "containerRef" in src and "terminal-container" in src, (
            "containerRef not attached to terminal-container"
        )
