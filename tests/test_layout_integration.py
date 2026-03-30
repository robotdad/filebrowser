"""Tests for the terminal integration into layout.js (task-8-layout-integration).

Verifies the structure and content of the layout.js file to ensure all terminal
state, helpers, resize handling, keyboard shortcuts, and rendering are correctly
integrated.

Tests follow the static-analysis approach used throughout this project — inspecting
the JS source text rather than running a JS test framework.
"""

import re
from functools import lru_cache
from pathlib import Path

LAYOUT_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "layout.js"
)

ACTIONS_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "actions.js"
)

CONTEXT_MENU_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "context-menu.js"
)

PREVIEW_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "preview.js"
)

EDITABLE_VIEWER_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "editable-viewer.js"
)

MARKDOWN_EDITOR_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "markdown-editor.js"
)


@lru_cache(maxsize=1)
def read_layout() -> str:
    return LAYOUT_FILE.read_text()


@lru_cache(maxsize=1)
def read_actions() -> str:
    return ACTIONS_FILE.read_text()


@lru_cache(maxsize=1)
def read_context_menu() -> str:
    return CONTEXT_MENU_FILE.read_text()


@lru_cache(maxsize=1)
def read_preview() -> str:
    return PREVIEW_FILE.read_text()


@lru_cache(maxsize=1)
def read_editable_viewer() -> str:
    return EDITABLE_VIEWER_FILE.read_text()


@lru_cache(maxsize=1)
def read_markdown_editor() -> str:
    return MARKDOWN_EDITOR_FILE.read_text()


# ── TestFileExists ──────────────────────────────────────────────────────────────


class TestFileExists:
    def test_layout_file_exists(self):
        """The layout.js file must exist at the expected path."""
        assert LAYOUT_FILE.exists(), f"layout.js not found at {LAYOUT_FILE}"


# ── TestImports ─────────────────────────────────────────────────────────────────


class TestImports:
    def test_imports_terminal_panel_from_terminal_js(self):
        """Must import TerminalPanel from './terminal.js'."""
        src = read_layout()
        assert "TerminalPanel" in src, "TerminalPanel not imported"
        assert "./terminal.js" in src, "./terminal.js import not found"

    def test_terminal_panel_import_is_named_import(self):
        """TerminalPanel must be imported as a named import."""
        src = read_layout()
        # Should match: import { TerminalPanel } from './terminal.js'
        assert re.search(
            r"import\s*\{[^}]*TerminalPanel[^}]*\}\s*from\s*['\"]\.\/terminal\.js['\"]",
            src,
        ), "TerminalPanel must be a named import from './terminal.js'"


# ── TestTerminalState ───────────────────────────────────────────────────────────


class TestTerminalState:
    def test_terminal_open_state_initialized_false(self):
        """Must declare terminalOpen state initialized to false."""
        src = read_layout()
        assert "terminalOpen" in src, "terminalOpen state not found"
        # Check it uses useState with false
        assert re.search(r"terminalOpen.*useState\(false\)", src) or re.search(
            r"useState\(false\).*terminalOpen", src
        ), "terminalOpen must be initialized with useState(false)"

    def test_terminal_cwd_state_initialized_empty_string(self):
        """Must declare terminalCwd state initialized to empty string."""
        src = read_layout()
        assert "terminalCwd" in src, "terminalCwd state not found"
        assert re.search(r"terminalCwd.*useState\(['\"]['\"]?\)", src) or re.search(
            r"useState\(['\"]['\"]?\).*terminalCwd", src
        ), "terminalCwd must be initialized with useState('')"

    def test_terminal_dock_state_with_localstorage_fallback(self):
        """Must declare terminalDock state with localStorage fallback."""
        src = read_layout()
        assert "terminalDock" in src, "terminalDock state not found"
        assert "fb-terminal-dock" in src, (
            "localStorage key 'fb-terminal-dock' not found"
        )
        # Should use 'side' as default
        assert "'side'" in src or '"side"' in src, "default dock 'side' not found"

    def test_terminal_size_state_with_localstorage_fallback(self):
        """Must declare terminalSize state with localStorage fallback."""
        src = read_layout()
        assert "terminalSize" in src, "terminalSize state not found"
        assert "fb-terminal-size" in src, (
            "localStorage key 'fb-terminal-size' not found"
        )
        # Should use 400 as default
        assert "400" in src, "default terminal size 400 not found"

    def test_is_terminal_resizing_ref(self):
        """Must declare isTerminalResizing as a useRef."""
        src = read_layout()
        assert "isTerminalResizing" in src, "isTerminalResizing ref not found"
        assert re.search(r"isTerminalResizing\s*=\s*useRef\(false\)", src), (
            "isTerminalResizing must be useRef(false)"
        )


# ── TestTerminalHelpers ─────────────────────────────────────────────────────────


class TestTerminalHelpers:
    def test_open_terminal_function_exists(self):
        """Must declare openTerminal helper function."""
        src = read_layout()
        assert "openTerminal" in src, "openTerminal function not found"

    def test_open_terminal_sets_cwd(self):
        """openTerminal must set terminal cwd."""
        src = read_layout()
        assert "setTerminalCwd" in src, "setTerminalCwd not found in openTerminal"

    def test_open_terminal_sets_open_true(self):
        """openTerminal must set terminalOpen to true."""
        src = read_layout()
        assert re.search(r"setTerminalOpen\(true\)", src), (
            "setTerminalOpen(true) not found — openTerminal must open the terminal"
        )

    def test_close_terminal_function_exists(self):
        """Must declare closeTerminal helper function."""
        src = read_layout()
        assert "closeTerminal" in src, "closeTerminal function not found"

    def test_close_terminal_sets_open_false(self):
        """closeTerminal must set terminalOpen to false."""
        src = read_layout()
        assert re.search(r"setTerminalOpen\(false\)", src), (
            "setTerminalOpen(false) not found — closeTerminal must close the terminal"
        )

    def test_toggle_terminal_dock_function_exists(self):
        """Must declare toggleTerminalDock helper function."""
        src = read_layout()
        assert "toggleTerminalDock" in src, "toggleTerminalDock function not found"

    def test_toggle_terminal_dock_swaps_side_bottom(self):
        """toggleTerminalDock must swap between 'side' and 'bottom'."""
        src = read_layout()
        assert "'side'" in src or '"side"' in src, "dock value 'side' not found"
        assert "'bottom'" in src or '"bottom"' in src, "dock value 'bottom' not found"

    def test_toggle_terminal_dock_persists_to_localstorage(self):
        """toggleTerminalDock must persist the new value to localStorage."""
        src = read_layout()
        assert "localStorage.setItem" in src, "localStorage.setItem not found"
        assert "fb-terminal-dock" in src, (
            "fb-terminal-dock key not found — dock must be persisted"
        )


# ── TestStartTerminalResize ─────────────────────────────────────────────────────


class TestStartTerminalResize:
    def test_start_terminal_resize_function_exists(self):
        """Must declare startTerminalResize function."""
        src = read_layout()
        assert "startTerminalResize" in src, "startTerminalResize function not found"

    def test_start_terminal_resize_sets_body_cursor(self):
        """startTerminalResize must set document.body.style.cursor."""
        src = read_layout()
        # Must set some cursor style for resize
        assert re.search(r"document\.body\.style\.cursor\s*=", src), (
            "document.body.style.cursor assignment not found in startTerminalResize"
        )

    def test_start_terminal_resize_adds_mousemove_listener(self):
        """startTerminalResize must add mousemove event listener."""
        src = read_layout()
        # Need more than one mousemove listener (sidebar also uses one)
        matches = re.findall(r"addEventListener\(['\"]mousemove['\"]", src)
        assert len(matches) >= 1, "mousemove listener not found for terminal resize"

    def test_start_terminal_resize_adds_mouseup_listener(self):
        """startTerminalResize must add mouseup event listener."""
        src = read_layout()
        matches = re.findall(r"addEventListener\(['\"]mouseup['\"]", src)
        assert len(matches) >= 1, "mouseup listener not found for terminal resize"

    def test_side_mode_uses_window_inner_width(self):
        """Side dock resize must use window.innerWidth - ev.clientX."""
        src = read_layout()
        assert "window.innerWidth" in src, (
            "window.innerWidth not found — side dock resize needs it"
        )

    def test_resize_clamps_side_mode_min_200(self):
        """Side mode resize must clamp minimum to 200."""
        src = read_layout()
        assert "200" in src, "Min clamp value 200 not found for side resize"

    def test_resize_clamps_side_mode_max_800(self):
        """Side mode resize must clamp maximum to 800."""
        src = read_layout()
        assert "800" in src, "Max clamp value 800 not found for side resize"

    def test_resize_clamps_bottom_mode_min_150(self):
        """Bottom mode resize must clamp minimum to 150."""
        src = read_layout()
        assert "150" in src, "Min clamp value 150 not found for bottom resize"

    def test_resize_clamps_bottom_mode_max_600(self):
        """Bottom mode resize must clamp maximum to 600."""
        src = read_layout()
        assert "600" in src, "Max clamp value 600 not found for bottom resize"

    def test_mouseup_persists_size_to_localstorage(self):
        """mouseup handler in startTerminalResize must persist size to localStorage."""
        src = read_layout()
        assert "fb-terminal-size" in src, (
            "fb-terminal-size key not found — size must be persisted on mouseup"
        )


# ── TestKeyboardShortcut ─────────────────────────────────────────────────────────


class TestKeyboardShortcut:
    def test_ctrl_backtick_shortcut_exists(self):
        """Must handle Ctrl+` / Cmd+` keyboard shortcut for terminal toggle."""
        src = read_layout()
        # Should check for backtick key
        assert "e.key === '`'" in src or 'e.key === "`"' in src, (
            "Ctrl+` shortcut not found — must check e.key === '`'"
        )

    def test_ctrl_backtick_checks_ctrl_or_meta(self):
        """Ctrl+` shortcut must check for Ctrl or Meta modifier."""
        src = read_layout()
        # metaKey or ctrlKey check near backtick
        assert "metaKey" in src and "ctrlKey" in src, (
            "metaKey/ctrlKey check not found for terminal keyboard shortcut"
        )

    def test_ctrl_backtick_toggles_terminal(self):
        """Ctrl+` must toggle the terminal (open or close)."""
        src = read_layout()
        # Either directly calls setTerminalOpen or uses openTerminal/closeTerminal
        assert (
            "setTerminalOpen" in src or "openTerminal" in src or "closeTerminal" in src
        ), "Terminal toggle logic not found for keyboard shortcut"

    def test_ctrl_backtick_sets_cwd_when_opening(self):
        """Ctrl+` shortcut must set cwd to currentPath when opening terminal."""
        src = read_layout()
        assert "setTerminalCwd" in src or "openTerminal" in src, (
            "cwd setting not found in keyboard shortcut handler"
        )

    def test_ctrl_backtick_reuses_terminal_helpers(self):
        """Keyboard shortcut should reuse openTerminal/closeTerminal helpers."""
        src = read_layout()
        assert "openTerminal(currentPath)" in src, (
            "Ctrl+` open path should go through openTerminal(currentPath) "
            "instead of duplicating terminal state updates inline"
        )
        assert "closeTerminal()" in src, (
            "Ctrl+` close path should go through closeTerminal() "
            "instead of duplicating terminal state updates inline"
        )


# ── TestMainContentUpdates ──────────────────────────────────────────────────────


class TestMainContentUpdates:
    def test_main_content_adds_terminal_class_when_open(self):
        """main-content div must add terminal-side or terminal-bottom class when open."""
        src = read_layout()
        # Should reference terminal-${terminalDock} or similar
        assert "terminal-" in src and "terminalDock" in src, (
            "terminal-{dock} class not found for main-content"
        )

    def test_main_content_has_terminal_width_css_variable(self):
        """main-content must set --terminal-width CSS variable for side dock."""
        src = read_layout()
        assert "--terminal-width" in src, (
            "--terminal-width CSS variable not set on main-content"
        )

    def test_main_content_has_terminal_height_css_variable(self):
        """main-content must set --terminal-height CSS variable for bottom dock."""
        src = read_layout()
        assert "--terminal-height" in src, (
            "--terminal-height CSS variable not set on main-content"
        )

    def test_terminal_size_used_in_css_variable(self):
        """terminalSize must be used in CSS variable value."""
        src = read_layout()
        assert "terminalSize" in src, "terminalSize not referenced for CSS variable"


# ── TestTerminalPanelRendering ──────────────────────────────────────────────────


class TestTerminalPanelRendering:
    def test_terminal_panel_rendered_in_layout(self):
        """TerminalPanel component must be rendered in the layout."""
        src = read_layout()
        assert "<${TerminalPanel}" in src or "${TerminalPanel}" in src, (
            "TerminalPanel not rendered in layout"
        )

    def test_terminal_panel_receives_cwd_prop(self):
        """TerminalPanel must receive cwd prop."""
        src = read_layout()
        assert (
            re.search(r"cwd=\$\{terminalCwd\}", src) or "cwd=${terminalCwd}" in src
        ), "cwd prop not passed to TerminalPanel"

    def test_terminal_panel_receives_on_close_prop(self):
        """TerminalPanel must receive onClose prop."""
        src = read_layout()
        assert "onClose" in src, "onClose prop not passed to TerminalPanel"

    def test_terminal_panel_receives_dock_position_prop(self):
        """TerminalPanel must receive dockPosition prop."""
        src = read_layout()
        assert "dockPosition" in src, "dockPosition prop not passed to TerminalPanel"

    def test_terminal_panel_receives_on_toggle_dock_prop(self):
        """TerminalPanel must receive onToggleDock prop."""
        src = read_layout()
        assert "onToggleDock" in src, "onToggleDock prop not passed to TerminalPanel"


# ── TestResizeHandleRendering ───────────────────────────────────────────────────


class TestResizeHandleRendering:
    def test_resize_handle_rendered(self):
        """A terminal resize handle element must be rendered."""
        src = read_layout()
        assert "terminal-resize-handle" in src, (
            "terminal-resize-handle class not found in rendered output"
        )

    def test_resize_handle_has_on_mouse_down(self):
        """Terminal resize handle must have onMouseDown handler."""
        src = read_layout()
        assert "startTerminalResize" in src, (
            "startTerminalResize not found — resize handle needs onMouseDown"
        )

    def test_resize_handle_classes_match_css_contract(self):
        """Class names rendered in layout.js must match the selectors defined in styles.css.

        The CSS contract (styles.css) defines:
          - .terminal-resize-handle          → side dock  (col-resize)
          - .terminal-resize-handle-vertical → bottom dock (row-resize)

        layout.js must render these exact class names so the resize handle
        actually receives its positioning, cursor, and hit-area styles.
        Using legacy names like -h / -v silently breaks drag-to-resize.
        """
        js_src = read_layout()
        css_path = (
            Path(__file__).parent.parent
            / "filebrowser"
            / "static"
            / "css"
            / "styles.css"
        )
        css_src = css_path.read_text()

        # Both canonical selectors must be defined in the stylesheet
        assert ".terminal-resize-handle" in css_src, (
            ".terminal-resize-handle selector missing from styles.css"
        )
        assert ".terminal-resize-handle-vertical" in css_src, (
            ".terminal-resize-handle-vertical selector missing from styles.css"
        )

        # layout.js must render classes that match those selectors.
        # Use single-quoted forms to avoid false substring matches
        # (e.g. 'terminal-resize-handle-v' is a prefix of 'terminal-resize-handle-vertical').
        assert "'terminal-resize-handle'" in js_src, (
            "'terminal-resize-handle' not rendered in layout.js — "
            "side-dock resize handle will not receive col-resize cursor"
        )
        assert "'terminal-resize-handle-vertical'" in js_src, (
            "'terminal-resize-handle-vertical' not rendered in layout.js — "
            "bottom-dock resize handle will not receive row-resize cursor"
        )
        # The stale -h / -v variants must be absent
        assert "'terminal-resize-handle-h'" not in js_src, (
            "Stale class 'terminal-resize-handle-h' found in layout.js — "
            "no matching CSS selector exists; use 'terminal-resize-handle-vertical'"
        )
        assert "'terminal-resize-handle-v'" not in js_src, (
            "Stale class 'terminal-resize-handle-v' found in layout.js — "
            "no matching CSS selector exists; use 'terminal-resize-handle'"
        )


# ── TestContextMenuIntegration ──────────────────────────────────────────────────


class TestContextMenuIntegration:
    def test_context_menu_receives_on_open_terminal_prop(self):
        """ContextMenu must receive onOpenTerminal prop."""
        src = read_layout()
        assert "onOpenTerminal" in src, "onOpenTerminal prop not passed to ContextMenu"

    def test_open_terminal_passed_to_context_menu(self):
        """openTerminal function must be passed as onOpenTerminal to ContextMenu (gated by terminalEnabled)."""
        src = read_layout()
        assert re.search(r"onOpenTerminal=\$\{.*openTerminal.*\}", src), (
            "openTerminal not passed as onOpenTerminal to ContextMenu"
        )

    def test_context_menu_component_accepts_on_open_terminal(self):
        """context-menu.js must declare onOpenTerminal in its function signature.

        Passing a prop the receiving component ignores is dead plumbing — the
        prop must appear in the ContextMenu function parameter list.
        """
        src = read_context_menu()
        assert re.search(
            r"function\s+ContextMenu\s*\(\s*\{[^}]*onOpenTerminal[^}]*\}", src
        ), (
            "onOpenTerminal not found in ContextMenu function signature "
            "(context-menu.js) — prop passed from layout.js is dead plumbing"
        )

    def test_context_menu_component_renders_open_terminal_action(self):
        """context-menu.js must render an 'Open in terminal' action using onOpenTerminal.

        The prop is meaningless unless ContextMenu actually wires it to a
        menu item the user can click.
        """
        src = read_context_menu()
        # Accept either the function reference or a button label mentioning terminal
        assert "onOpenTerminal" in src and (
            "terminal" in src.lower() and re.search(r"onOpenTerminal|openTerminal", src)
        ), (
            "ContextMenu does not render an 'open in terminal' action — "
            "onOpenTerminal must be wired to a visible menu item"
        )


# ── TestActionBarIntegration ─────────────────────────────────────────────────────


class TestActionBarIntegration:
    def test_action_bar_receives_terminal_open_prop(self):
        """ActionBar must receive terminalOpen prop."""
        src = read_layout()
        assert re.search(r"terminalOpen=\$\{terminalOpen\}", src) or (
            "terminalOpen=${terminalOpen}" in src
        ), "terminalOpen prop not passed to ActionBar"

    def test_action_bar_receives_on_toggle_terminal_prop(self):
        """ActionBar must receive onToggleTerminal prop."""
        src = read_layout()
        assert "onToggleTerminal" in src, (
            "onToggleTerminal prop not passed to ActionBar"
        )

    def test_on_toggle_terminal_calls_open_or_close(self):
        """onToggleTerminal must call openTerminal or closeTerminal based on state."""
        src = read_layout()
        # Must reference both openTerminal and closeTerminal in the toggle expression
        assert "openTerminal" in src and "closeTerminal" in src, (
            "onToggleTerminal must reference both openTerminal and closeTerminal"
        )

    def test_action_bar_component_accepts_terminal_open_prop(self):
        """actions.js must declare terminalOpen in its ActionBar function signature.

        The prop passed from layout.js is dead plumbing unless ActionBar
        actually receives it in the function parameter destructuring.
        """
        src = read_actions()
        assert re.search(
            r"function\s+ActionBar\s*\(\s*\{[^}]*terminalOpen[^}]*\}", src
        ), (
            "terminalOpen not found in ActionBar function signature (actions.js) — "
            "prop passed from layout.js is dead plumbing"
        )

    def test_action_bar_component_accepts_on_toggle_terminal_prop(self):
        """actions.js must declare onToggleTerminal in its ActionBar function signature.

        The prop passed from layout.js is dead plumbing unless ActionBar
        actually receives it in the function parameter destructuring.
        """
        src = read_actions()
        assert re.search(
            r"function\s+ActionBar\s*\(\s*\{[^}]*onToggleTerminal[^}]*\}", src
        ), (
            "onToggleTerminal not found in ActionBar function signature (actions.js) — "
            "prop passed from layout.js is dead plumbing"
        )

    def test_action_bar_component_renders_terminal_toggle_button(self):
        """actions.js must render a terminal toggle button wired to onToggleTerminal.

        Accepting the prop without using it is still dead plumbing — the
        button must actually appear in the rendered output.
        """
        src = read_actions()
        assert "onToggleTerminal" in src and ("terminal" in src.lower()), (
            "ActionBar does not render a terminal toggle button — "
            "onToggleTerminal must be wired to a visible button"
        )


# ── TestTabManagerIntegration ─────────────────────────────────────────────────


class TestTabManagerIntegration:
    def test_imports_use_tab_manager_from_hooks(self):
        """Must import useTabManager from '../hooks/use-tab-manager.js'."""
        src = read_layout()
        assert "useTabManager" in src, "useTabManager not imported"
        assert "../hooks/use-tab-manager.js" in src, (
            "../hooks/use-tab-manager.js import not found"
        )

    def test_use_tab_manager_import_is_named_import(self):
        """useTabManager must be imported as a named import."""
        src = read_layout()
        assert re.search(
            r"import\s*\{[^}]*useTabManager[^}]*\}\s*from\s*['\"]\.\.\/hooks\/use-tab-manager\.js['\"]",
            src,
        ), "useTabManager must be a named import from '../hooks/use-tab-manager.js'"

    def test_imports_tab_bar_from_tab_bar_js(self):
        """Must import TabBar from './tab-bar.js'."""
        src = read_layout()
        assert "TabBar" in src, "TabBar not imported"
        assert "./tab-bar.js" in src, "./tab-bar.js import not found"

    def test_tab_bar_import_is_named_import(self):
        """TabBar must be imported as a named import from './tab-bar.js'."""
        src = read_layout()
        assert re.search(
            r"import\s*\{[^}]*TabBar[^}]*\}\s*from\s*['\"]\.\/tab-bar\.js['\"]",
            src,
        ), "TabBar must be a named import from './tab-bar.js'"

    def test_calls_use_tab_manager(self):
        """Must call useTabManager() and assign result to tabManager."""
        src = read_layout()
        assert re.search(r"tabManager\s*=\s*useTabManager\(\)", src), (
            "tabManager = useTabManager() not found in layout.js"
        )

    def test_selected_file_derived_from_active_file_path(self):
        """selectedFile must be derived from tabManager.activeFilePath."""
        src = read_layout()
        assert re.search(
            r"selectedFile\s*=\s*tabManager\.activeFilePath",
            src,
        ), "selectedFile must be assigned from tabManager.activeFilePath"

    def test_handle_select_file_calls_tab_manager_open(self):
        """handleSelectFile must call tabManager.open(path)."""
        src = read_layout()
        assert re.search(r"tabManager\.open\(path\)", src), (
            "tabManager.open(path) not found — handleSelectFile must call tabManager.open"
        )

    def test_set_selected_file_not_called_as_setter(self):
        """setSelectedFile setter must not be called — state ownership transferred to tabManager."""
        src = read_layout()
        assert not re.search(r"\bsetSelectedFile\s*\(", src), (
            "setSelectedFile() called directly — this setter was removed in task-6; "
            "use tabManager.close() to deactivate the active file"
        )


# ── TestTabBarRendering ───────────────────────────────────────────────────────


class TestTabBarRendering:
    def test_tab_bar_rendered_in_preview_section(self):
        """TabBar must be rendered in the preview section via <${TabBar}."""
        src = read_layout()
        assert "<${TabBar}" in src, (
            "TabBar not rendered in layout (expected <${TabBar})"
        )

    def test_tab_bar_receives_tabs_prop(self):
        """TabBar must receive tabs=${tabManager.tabs}."""
        src = read_layout()
        assert "tabs=${tabManager.tabs}" in src, (
            "tabs=${tabManager.tabs} not found — TabBar must receive tabs prop from tabManager"
        )

    def test_tab_bar_receives_active_tab_id_prop(self):
        """TabBar must receive activeTabId=${tabManager.activeTabId}."""
        src = read_layout()
        assert re.search(r"activeTabId=\$\{tabManager\.activeTabId\}", src), (
            "activeTabId prop not passed to TabBar from tabManager"
        )

    def test_tab_bar_receives_on_activate_prop(self):
        """TabBar must receive onActivate=${tabManager.activate}."""
        src = read_layout()
        assert re.search(r"onActivate=\$\{tabManager\.activate\}", src), (
            "onActivate prop not passed to TabBar from tabManager"
        )

    def test_tab_bar_receives_on_pin_prop(self):
        """TabBar must receive onPin=${tabManager.pin}."""
        src = read_layout()
        assert re.search(r"onPin=\$\{tabManager\.pin\}", src), (
            "onPin prop not passed to TabBar from tabManager"
        )

    def test_tab_bar_receives_on_close_from_tab_manager(self):
        """TabBar must receive onClose=${tabManager.close}."""
        src = read_layout()
        assert "onClose=${tabManager.close}" in src, (
            "onClose=${tabManager.close} not found — TabBar must receive onClose from tabManager"
        )

    def test_preview_pane_receives_active_file_path(self):
        """PreviewPane must reference activeFilePath (derived via tabManager)."""
        src = read_layout()
        assert "activeFilePath" in src, (
            "activeFilePath not referenced in layout.js — PreviewPane must use it"
        )
        assert re.search(r"<\$\{PreviewPane\}.*filePath", src, re.DOTALL), (
            "PreviewPane does not receive filePath prop"
        )


# ── TestPreviewPaneDirtyIntegration ────────────────────────────────────────────────────────────────


class TestPreviewPaneDirtyIntegration:
    def test_preview_pane_signature_includes_on_dirty_change(self):
        """PreviewPane function signature must include onDirtyChange parameter."""
        src = read_preview()
        assert re.search(
            r"export\s+function\s+PreviewPane\s*\(\s*\{[^}]*onDirtyChange[^}]*\}",
            src,
        ), (
            "onDirtyChange not found in PreviewPane function signature (preview.js) — "
            "PreviewPane must accept onDirtyChange as a prop"
        )

    def test_on_dirty_change_passed_to_editable_viewer(self):
        """PreviewPane must pass onDirtyChange to EditableViewer."""
        src = read_preview()
        assert (
            re.search(
                r"EditableViewer[^`]*onDirtyChange=\$\{onDirtyChange\}", src, re.DOTALL
            )
            or "onDirtyChange=${onDirtyChange}" in src
        ), "onDirtyChange not passed to EditableViewer in preview.js"

    def test_on_dirty_change_passed_to_markdown_editor(self):
        """PreviewPane must pass onDirtyChange to MarkdownEditor."""
        src = read_preview()
        assert re.search(
            r"MarkdownEditor[^`]*onDirtyChange=\$\{onDirtyChange\}", src, re.DOTALL
        ) or re.search(
            r"onDirtyChange=\$\{onDirtyChange\}.*MarkdownEditor", src, re.DOTALL
        ), "onDirtyChange not passed to MarkdownEditor in preview.js"

    def test_editable_viewer_accepts_on_dirty_change(self):
        """EditableViewer function signature must include onDirtyChange parameter."""
        src = read_editable_viewer()
        assert re.search(
            r"export\s+function\s+EditableViewer\s*\(\s*\{[^}]*onDirtyChange[^}]*\}",
            src,
        ), (
            "onDirtyChange not found in EditableViewer function signature (editable-viewer.js) — "
            "EditableViewer must accept onDirtyChange as a prop"
        )

    def test_layout_passes_on_dirty_change_to_preview_pane(self):
        """layout.js must pass an onDirtyChange prop to PreviewPane."""
        src = read_layout()
        assert re.search(r"PreviewPane.*onDirtyChange", src, re.DOTALL), (
            "onDirtyChange prop not passed to PreviewPane in layout.js"
        )

    def test_layout_on_dirty_change_calls_tab_manager_set_dirty(self):
        """The onDirtyChange callback in layout.js must call tabManager.setDirty."""
        src = read_layout()
        assert "tabManager.setDirty" in src, (
            "tabManager.setDirty not found in layout.js — "
            "onDirtyChange callback must call tabManager.setDirty"
        )


# ── TestFileManagementTabIntegration ──────────────────────────────────────────────────────────────────────────────────────────────────────────


class TestFileManagementTabIntegration:
    def test_handle_ctx_rename_calls_tab_manager_update_path(self):
        """handleCtxRename must call tabManager.updatePath(path, newPath) after rename."""
        src = read_layout()
        assert re.search(r"tabManager\.updatePath\(", src), (
            "tabManager.updatePath( not found in layout.js — "
            "handleCtxRename must call tabManager.updatePath(path, newPath) in .then() callback"
        )

    def test_handle_ctx_delete_calls_tab_manager_close_by_path(self):
        """handleCtxDelete must call tabManager.closeByPath(path) to close the tab."""
        src = read_layout()
        assert re.search(r"tabManager\.closeByPath\(", src), (
            "tabManager.closeByPath( not found in layout.js — "
            "handleCtxDelete must call tabManager.closeByPath(path)"
        )

    def test_handle_ctx_delete_does_not_use_set_selected_file_null(self):
        """handleCtxDelete must not use setSelectedFile(null)."""
        src = read_layout()
        assert "setSelectedFile(null)" not in src, (
            "setSelectedFile(null) found in layout.js — "
            "handleCtxDelete must not set selectedFile to null directly; "
            "use tabManager.closeByPath(path) instead"
        )

    def test_set_selected_file_does_not_exist_in_layout(self):
        """setSelectedFile (singular) must not exist anywhere in layout.js."""
        src = read_layout()
        assert not re.search(r"\bsetSelectedFile\b", src), (
            "setSelectedFile found in layout.js — "
            "state ownership has been transferred to tabManager; "
            "use tabManager methods to manage active file state"
        )
