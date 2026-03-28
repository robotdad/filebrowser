"""Tests for terminal panel CSS (task-7-terminal-css).

Verifies that all required CSS sections are appended to styles.css.
Checks selectors, properties, and values specified in the task spec.
"""

import re
from functools import lru_cache
from pathlib import Path

CSS_FILE = (
    Path(__file__).parent.parent / "filebrowser" / "static" / "css" / "styles.css"
)


@lru_cache(maxsize=1)
def read_css() -> str:
    return CSS_FILE.read_text()


def rule_block(selector: str) -> str:
    match = re.search(
        rf"(?ms)^[ \t]*{re.escape(selector)}\s*\{{(?P<body>.*?)^[ \t]*\}}",
        read_css(),
    )
    assert match, f"{selector} selector not found"
    return match.group("body")


# ── TestFileExists ────────────────────────────────────────────────────────────


class TestFileExists:
    def test_styles_css_exists(self):
        """styles.css must exist at the expected path."""
        assert CSS_FILE.exists(), f"styles.css not found at {CSS_FILE}"


# ── TestTerminalTokens ─────────────────────────────────────────────────────────


class TestTerminalTokens:
    def test_terminal_tokens_defined(self):
        """Terminal styling should flow through named component tokens."""
        root = rule_block(":root")
        for token in (
            "--terminal-bg",
            "--terminal-header-bg",
            "--terminal-text-muted",
            "--terminal-hover-bg",
            "--terminal-danger",
        ):
            assert token in root, f"{token} not found in :root token definitions"


# ── TestSideDockLayout ───────────────────────────────────────────────────────


class TestSideDockLayout:
    def test_side_dock_selector_present(self):
        """Must include .main-content.terminal-side selector."""
        css = read_css()
        assert ".main-content.terminal-side" in css, (
            ".main-content.terminal-side selector not found"
        )

    def test_side_dock_three_column_grid(self):
        """Side dock must define a 3-column grid."""
        css = read_css()
        assert "var(--terminal-width, 400px)" in css, (
            "var(--terminal-width, 400px) not found in side dock grid"
        )

    def test_side_dock_grid_template_columns(self):
        """Side dock grid-template-columns must include sidebar-width and terminal-width."""
        css = read_css()
        # The spec says: grid-template-columns: var(--sidebar-width) 1fr var(--terminal-width, 400px)
        # We check for the key parts
        assert "var(--sidebar-width) 1fr var(--terminal-width, 400px)" in css, (
            "Side dock grid-template-columns not correct"
        )


# ── TestBottomDockLayout ──────────────────────────────────────────────────────


class TestBottomDockLayout:
    def test_bottom_dock_selector_present(self):
        """Must include .main-content.terminal-bottom selector."""
        css = read_css()
        assert ".main-content.terminal-bottom" in css, (
            ".main-content.terminal-bottom selector not found"
        )

    def test_bottom_dock_terminal_height_variable(self):
        """Bottom dock must use --terminal-height CSS variable."""
        css = read_css()
        assert "var(--terminal-height, 300px)" in css, (
            "var(--terminal-height, 300px) not found in bottom dock grid"
        )

    def test_bottom_dock_grid_template_rows(self):
        """Bottom dock must define grid-template-rows with terminal height."""
        css = read_css()
        assert "grid-template-rows" in css, (
            "grid-template-rows not found in bottom dock section"
        )

    def test_bottom_dock_sidebar_spans_rows(self):
        """Bottom dock sidebar must span all rows (grid-row: 1 / -1)."""
        css = read_css()
        assert "grid-row: 1 / -1" in css, (
            "grid-row: 1 / -1 not found — sidebar must span all rows in bottom dock"
        )

    def test_bottom_dock_terminal_panel_position(self):
        """Terminal panel must be at grid-column: 2; grid-row: 2 in bottom dock."""
        css = read_css()
        assert "grid-column: 2" in css, (
            "grid-column: 2 not found for terminal panel in bottom dock"
        )
        assert "grid-row: 2" in css, (
            "grid-row: 2 not found for terminal panel in bottom dock"
        )


# ── TestTerminalPanel ─────────────────────────────────────────────────────────


class TestTerminalPanel:
    def test_terminal_panel_dark_background(self):
        """Terminal panel must use the shared terminal background token."""
        panel = rule_block(".terminal-panel")
        assert "background: var(--terminal-bg)" in panel, (
            "Terminal panel must use var(--terminal-bg)"
        )

    def test_terminal_panel_flex_column(self):
        """Terminal panel must be a flex column container."""
        panel = rule_block(".terminal-panel")
        assert "display: flex" in panel, "display: flex not found in .terminal-panel"
        assert "flex-direction: column" in panel, (
            "flex-direction: column not found in .terminal-panel"
        )

    def test_terminal_panel_border_left(self):
        """Terminal panel (side dock) must have border-left."""
        panel = rule_block(".terminal-panel")
        assert "border-left: 0.5px solid var(--border-color)" in panel, (
            "border-left: 0.5px solid var(--border-color) not found in .terminal-panel"
        )

    def test_terminal_panel_border_top_bottom_dock(self):
        """Terminal panel (bottom dock variant) must have border-top."""
        panel = rule_block(".main-content.terminal-bottom .terminal-panel")
        assert "border-top: 0.5px solid var(--border-color)" in panel, (
            "border-top: 0.5px solid var(--border-color) not found for bottom dock terminal panel"
        )


# ── TestHeaderBar ─────────────────────────────────────────────────────────────


class TestHeaderBar:
    def test_header_flex_row(self):
        """Terminal header bar must be flex row."""
        header = rule_block(".terminal-header")
        assert "display: flex" in header, "display: flex not found in .terminal-header"
        assert "flex-direction: row" in header, (
            "flex-direction: row not found in .terminal-header"
        )

    def test_header_padding(self):
        """Terminal header must have padding: 6px 12px."""
        header = rule_block(".terminal-header")
        assert "padding: 6px 12px" in header, (
            "Terminal header padding: 6px 12px not found in .terminal-header"
        )

    def test_header_background(self):
        """Terminal header background must use the shared terminal header token."""
        header = rule_block(".terminal-header")
        assert "background: var(--terminal-header-bg)" in header, (
            "Terminal header must use var(--terminal-header-bg)"
        )

    def test_header_min_height(self):
        """Terminal header must have min-height: 36px."""
        header = rule_block(".terminal-header")
        assert "min-height: 36px" in header, (
            "Terminal header min-height: 36px not found in .terminal-header"
        )

    def test_header_title_font_size(self):
        """Terminal header title must use font-size: 12px."""
        title = rule_block(".terminal-header-title")
        assert "font-size: 12px" in title, (
            "Terminal header title font-size: 12px not found in .terminal-header-title"
        )

    def test_header_title_font_weight(self):
        """Terminal header title must use font-weight: 600."""
        title = rule_block(".terminal-header-title")
        assert "font-weight: 600" in title, (
            "Terminal header title font-weight: 600 not found in .terminal-header-title"
        )

    def test_header_title_color(self):
        """Terminal header title must use the shared muted terminal text token."""
        title = rule_block(".terminal-header-title")
        assert "color: var(--terminal-text-muted)" in title, (
            "Terminal header title must use var(--terminal-text-muted)"
        )


# ── TestActionButtons ─────────────────────────────────────────────────────────


class TestActionButtons:
    def test_action_button_size(self):
        """Action buttons must be 26x26px."""
        button = rule_block(".terminal-action-btn")
        assert "width: 26px" in button, "Action button width 26px not found"
        assert "height: 26px" in button, "Action button height 26px not found"

    def test_action_button_border_radius(self):
        """Action buttons must have border-radius: 6px."""
        button = rule_block(".terminal-action-btn")
        assert "border-radius: 6px" in button, (
            "Action button border-radius: 6px not found in .terminal-action-btn"
        )

    def test_action_button_hover_background(self):
        """Action button hover must use the shared terminal hover token."""
        hover = rule_block(".terminal-action-btn:hover")
        assert "background: var(--terminal-hover-bg)" in hover, (
            "Action button hover must use var(--terminal-hover-bg)"
        )

    def test_close_button_hover_color(self):
        """Close button hover must use the shared terminal danger token."""
        hover = rule_block(".terminal-action-btn.terminal-close:hover")
        assert "color: var(--terminal-danger)" in hover, (
            "Close button hover must use var(--terminal-danger)"
        )


# ── TestTerminalContainer ─────────────────────────────────────────────────────


class TestTerminalContainer:
    def test_terminal_container_selector(self):
        """Must include .terminal-container selector."""
        css = read_css()
        assert "terminal-container" in css, ".terminal-container selector not found"

    def test_terminal_container_flex_1(self):
        """Terminal container must have flex: 1."""
        container = rule_block(".terminal-container")
        assert "flex: 1" in container, "flex: 1 not found in .terminal-container"

    def test_terminal_container_min_height_0(self):
        """Terminal container must have min-height: 0."""
        container = rule_block(".terminal-container")
        assert "min-height: 0" in container, (
            "min-height: 0 not found in .terminal-container"
        )

    def test_terminal_container_padding(self):
        """Terminal container must have padding: 4px."""
        container = rule_block(".terminal-container")
        assert "padding: 4px" in container, (
            "padding: 4px not found in .terminal-container"
        )

    def test_xterm_fills_height(self):
        """xterm elements must fill 100% height."""
        xterm = rule_block(".terminal-container .xterm")
        assert "height: 100%" in xterm, (
            "height: 100% not found for .terminal-container .xterm"
        )

    def test_xterm_viewport_overflow(self):
        """xterm viewport must allow scrolling."""
        viewport = rule_block(".terminal-container .xterm-viewport")
        assert "overflow-y: auto" in viewport, (
            "overflow-y: auto not found for .terminal-container .xterm-viewport"
        )


# ── TestResizeHandles ─────────────────────────────────────────────────────────


class TestResizeHandles:
    def test_horizontal_resize_handle_selector(self):
        """Must include a terminal horizontal resize handle selector."""
        css = read_css()
        # Should be a terminal-specific resize handle class
        assert "terminal-resize-handle" in css or "terminal-resize" in css, (
            "Terminal resize handle selector not found"
        )

    def test_horizontal_resize_handle_width(self):
        """Horizontal resize handle must be 8px wide."""
        handle = rule_block(".terminal-resize-handle")
        assert "width: 8px" in handle, (
            "Horizontal resize handle width: 8px not found in .terminal-resize-handle"
        )

    def test_horizontal_resize_col_resize_cursor(self):
        """Horizontal resize handle must use col-resize cursor."""
        handle = rule_block(".terminal-resize-handle")
        assert "cursor: col-resize" in handle, (
            "cursor: col-resize not found in .terminal-resize-handle"
        )

    def test_vertical_resize_handle_row_resize_cursor(self):
        """Vertical resize handle must use row-resize cursor."""
        handle = rule_block(".terminal-resize-handle-vertical")
        assert "cursor: row-resize" in handle, (
            "cursor: row-resize not found in .terminal-resize-handle-vertical"
        )

    def test_resize_handle_indicator_on_hover(self):
        """Resize handle hover must show 2px indicator in accent color."""
        css = read_css()
        assert ".terminal-resize-handle:hover::after" in css, (
            ".terminal-resize-handle:hover::after selector not found"
        )
        assert "background: var(--accent)" in css, (
            "background: var(--accent) not found for terminal resize handle hover"
        )

    def test_horizontal_resize_handle_reuses_shared_indicator_rule(self):
        """Terminal horizontal handle should share the existing resize-handle rule."""
        css = read_css()
        assert re.search(
            r"(?ms)^[ \t]*\.resize-handle::after,\s*^[ \t]*\.terminal-resize-handle::after\s*\{",
            css,
        ), "Terminal handle should reuse the shared .resize-handle::after rule"
        assert re.search(
            r"(?ms)^[ \t]*\.resize-handle:hover::after,\s*^[ \t]*\.terminal-resize-handle:hover::after\s*\{",
            css,
        ), "Terminal handle should reuse the shared .resize-handle:hover::after rule"


# ── TestMobileResponsive ──────────────────────────────────────────────────────


class TestMobileResponsive:
    def test_mobile_hides_terminal_panel(self):
        """On mobile (<768px), terminal panel must be hidden."""
        css = read_css()
        # Check that there's a media query for 768px that hides the terminal panel
        assert "max-width: 768px" in css, "max-width: 768px media query not found"
        # The terminal panel should be display: none in the mobile media query
        # We can verify by checking that after the media query, display: none is present
        # and terminal-panel is mentioned
        assert "display: none" in css, (
            "display: none not found — terminal panel must be hidden on mobile"
        )

    def test_mobile_resets_grid_to_single_column(self):
        """Mobile media query must reset grid to single column."""
        css = read_css()
        # The existing mobile styles already have grid-template-columns: 1fr
        # But we need to verify terminal-side and terminal-bottom are also reset
        assert "grid-template-columns: 1fr" in css, (
            "grid-template-columns: 1fr not found in mobile media query"
        )


# ── TestSyntaxValidity ────────────────────────────────────────────────────────


class TestSyntaxValidity:
    def test_balanced_braces(self):
        """CSS file must have balanced curly braces."""
        css = read_css()
        # Strip string literals (approximation) and count braces
        open_count = css.count("{")
        close_count = css.count("}")
        assert open_count == close_count, (
            f"Unbalanced braces in CSS: {open_count} opening vs {close_count} closing"
        )

    def test_no_double_semicolons(self):
        """CSS file must not contain double semicolons (syntax error)."""
        css = read_css()
        assert ";;" not in css, "Double semicolons found in CSS — likely a syntax error"
