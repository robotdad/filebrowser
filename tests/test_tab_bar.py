"""Tests for the TabBar Preact component (task-4-tab-bar).

Verifies the structure and content of the JS component file rather than
running a JS test framework — consistent with how test_terminal_component.py
and test_context_menu.py test the static frontend assets.
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
    / "tab-bar.js"
)

CSS_FILE = (
    Path(__file__).parent.parent / "filebrowser" / "static" / "css" / "styles.css"
)


TAB_BAR_SECTION_LOOKAHEAD = 2000  # tab bar CSS block is ~800 chars; 2000 is safe


@lru_cache(maxsize=1)
def read_component() -> str:
    return COMPONENT_FILE.read_text()


@lru_cache(maxsize=1)
def read_css() -> str:
    return CSS_FILE.read_text()


# ── TestFileExists ─────────────────────────────────────────────────────────────


class TestFileExists:
    def test_tab_bar_file_exists(self):
        """The component file must exist at the expected path."""
        assert COMPONENT_FILE.exists(), f"tab-bar.js not found at {COMPONENT_FILE}"


# ── TestImports ────────────────────────────────────────────────────────────────


class TestImports:
    def test_imports_html_from_html_js(self):
        """Must import html from '../html.js'."""
        src = read_component()
        assert "../html.js" in src, "html import from ../html.js not found"

    def test_imports_create_logger_from_logger_js(self):
        """Must import createLogger from 'logger.js'."""
        src = read_component()
        assert "createLogger" in src, "createLogger not imported"
        assert "logger.js" in src, "logger.js import not found"


# ── TestExports ────────────────────────────────────────────────────────────────


class TestExports:
    def test_exports_tab_bar_as_named_function(self):
        """Component must export TabBar as a named function."""
        src = read_component()
        assert "export function TabBar" in src or "export { TabBar" in src, (
            "TabBar is not exported as a named function"
        )


# ── TestProps ──────────────────────────────────────────────────────────────────


class TestProps:
    def test_accepts_tabs_prop(self):
        """Component must accept a tabs prop in destructured signature."""
        src = read_component()
        assert re.search(r"function\s+TabBar\s*\(\s*\{[^}]*\btabs\b[^}]*\}", src), (
            "tabs prop not found in TabBar function signature"
        )

    def test_accepts_active_tab_id_prop(self):
        """Component must accept an activeTabId prop in destructured signature."""
        src = read_component()
        assert re.search(
            r"function\s+TabBar\s*\(\s*\{[^}]*\bactiveTabId\b[^}]*\}", src
        ), "activeTabId prop not found in TabBar function signature"

    def test_accepts_on_activate_prop(self):
        """Component must accept an onActivate prop in destructured signature."""
        src = read_component()
        assert re.search(
            r"function\s+TabBar\s*\(\s*\{[^}]*\bonActivate\b[^}]*\}", src
        ), "onActivate prop not found in TabBar function signature"

    def test_accepts_on_pin_prop(self):
        """Component must accept an onPin prop in destructured signature."""
        src = read_component()
        assert re.search(r"function\s+TabBar\s*\(\s*\{[^}]*\bonPin\b[^}]*\}", src), (
            "onPin prop not found in TabBar function signature"
        )

    def test_accepts_on_close_prop(self):
        """Component must accept an onClose prop in destructured signature."""
        src = read_component()
        assert re.search(r"function\s+TabBar\s*\(\s*\{[^}]*\bonClose\b[^}]*\}", src), (
            "onClose prop not found in TabBar function signature"
        )


# ── TestRendering ──────────────────────────────────────────────────────────────


class TestRendering:
    def test_renders_container_with_file_tab_bar_class(self):
        """Must render a container element with class 'file-tab-bar'."""
        src = read_component()
        assert "file-tab-bar" in src, "'file-tab-bar' CSS class not found in component"

    def test_displays_basename_via_split_pop(self):
        """Must display basename using split('/').pop() pattern."""
        src = read_component()
        assert re.search(r"split\s*\(\s*['\"]\/['\"]\s*\)\s*\.pop\s*\(\s*\)", src), (
            "split('/').pop() pattern not found — basename must be extracted this way"
        )

    def test_basename_reads_tab_file_path_not_tab_path(self):
        """Basename extraction must use tab.filePath (the data model field), not tab.path.

        The tab data model stores the path as ``tab.filePath``.  Reading the
        wrong property (``tab.path``) silently returns ``undefined``, which
        causes the tab label to fall back to the raw tab ID (e.g. "tab-1").
        """
        src = read_component()
        assert "tab.filePath" in src, (
            "tab.filePath not found — basename must be read from tab.filePath"
        )
        # Find the basename extraction line and confirm it uses the correct field.
        basename_line = next(
            (line for line in src.splitlines() if "basename" in line and "split" in line),
            None,
        )
        assert basename_line is not None, "basename / split line not found in component"
        assert "tab.filePath" in basename_line, (
            f"basename line does not use tab.filePath: {basename_line.strip()!r}"
        )
        # Guard against the old wrong property silently regressing.
        # Remove "tab.filePath" first so a hypothetical "tab.filePath || tab.path"
        # expression doesn't mask a bare "tab.path" reference.
        without_file_path = basename_line.replace("tab.filePath", "")
        assert "tab.path" not in without_file_path, (
            "basename line still references bare tab.path — must use tab.filePath"
        )

    def test_renders_push_pin_icon(self):
        """Must render a push-pin icon with the ph base class for Phosphor font rendering."""
        src = read_component()
        assert "ph-push-pin" in src, "ph-push-pin icon not found in component"
        # The ph base class is required for Phosphor icon font to render — without it icons
        # appear as empty boxes. Every other component uses the two-class pattern: ph ph-<name>.
        assert re.search(r"ph ph-push-pin", src), (
            "ph base class missing from push-pin icon — must use 'ph ph-push-pin' pattern"
        )

    def test_renders_close_button_with_file_tab_close_class(self):
        """Must render a close button with class 'file-tab-close'."""
        src = read_component()
        assert "file-tab-close" in src, (
            "'file-tab-close' CSS class not found on close button"
        )

    def test_close_button_calls_on_close(self):
        """Close button must call onClose."""
        src = read_component()
        assert "onClose" in src, "onClose not referenced in component"
        # Find close button context and verify onClose is wired up
        assert re.search(r"file-tab-close", src), "file-tab-close class not found"
        # onClose must appear near the close button
        close_idx = src.find("file-tab-close")
        surrounding = src[max(0, close_idx - 300) : close_idx + 300]
        assert "onClose" in surrounding, (
            "onClose not found near file-tab-close button — close button must call onClose"
        )

    def test_pin_button_calls_on_pin(self):
        """Pin button must call onPin."""
        src = read_component()
        assert "onPin" in src, "onPin not referenced in component"
        # The push-pin element must wire to onPin
        pin_idx = src.find("ph-push-pin")
        surrounding = src[max(0, pin_idx - 300) : pin_idx + 300]
        assert "onPin" in surrounding, (
            "onPin not found near ph-push-pin icon — pin button must call onPin"
        )


# ── TestActiveState ────────────────────────────────────────────────────────────


class TestActiveState:
    def test_active_tab_has_active_css_class_using_active_tab_id_comparison(self):
        """Active tab must use activeTabId comparison to apply 'active' CSS class."""
        src = read_component()
        # Must reference activeTabId and use it to conditionally apply 'active' class
        assert "activeTabId" in src, "activeTabId not referenced in component"
        assert re.search(r"activeTabId", src), "activeTabId comparison not found"
        # The 'active' class must be conditionally applied
        assert re.search(r"active", src), "'active' CSS class not referenced"
        # Together: activeTabId used for active class check
        assert re.search(r"activeTabId.*active|active.*activeTabId", src, re.DOTALL), (
            "activeTabId must be used to determine which tab gets the 'active' CSS class"
        )


# ── TestDirtyIndicator ─────────────────────────────────────────────────────────


class TestDirtyIndicator:
    def test_renders_element_with_file_tab_dirty_class(self):
        """Must render an element with class 'file-tab-dirty'."""
        src = read_component()
        assert "file-tab-dirty" in src, (
            "'file-tab-dirty' CSS class not found in component"
        )

    def test_dirty_indicator_is_conditional_on_tab_dirty(self):
        """Dirty indicator must be conditional on tab.dirty."""
        src = read_component()
        assert re.search(r"tab\.dirty", src), (
            "tab.dirty not found — dirty indicator must be conditional on tab.dirty"
        )
        # tab.dirty should gate the dirty indicator
        dirty_prop_idx = src.find("tab.dirty")
        surrounding = src[max(0, dirty_prop_idx - 100) : dirty_prop_idx + 200]
        assert "file-tab-dirty" in surrounding or re.search(
            r"tab\.dirty.*file-tab-dirty|file-tab-dirty.*tab\.dirty",
            src,
            re.DOTALL,
        ), "tab.dirty must be used to conditionally render the file-tab-dirty element"


# ── TestEmptyState ─────────────────────────────────────────────────────────────


class TestEmptyState:
    def test_returns_null_when_tabs_array_is_empty(self):
        """Must return null when tabs array is empty or missing."""
        src = read_component()
        # Component must have a null return guard for empty/missing tabs
        assert re.search(r"return\s+null", src), (
            "No 'return null' guard found — component must return null for empty tabs"
        )
        # The guard must reference tabs
        assert re.search(r"(!\s*tabs|tabs\.length|!tabs)", src), (
            "tabs emptiness check not found — must guard against empty/missing tabs array"
        )


# ── TestLogging ────────────────────────────────────────────────────────────────


class TestLogging:
    def test_creates_logger_named_tab_bar(self):
        """Must create a logger named 'TabBar'."""
        src = read_component()
        assert re.search(r"createLogger\s*\(\s*['\"]TabBar['\"]\s*\)", src), (
            "createLogger('TabBar') not found — must create a logger with name 'TabBar'"
        )


# ── TestCssClasses ────────────────────────────────────────────────────────────


class TestCssClasses:
    def test_file_tab_bar_selector_exists(self):
        """.file-tab-bar CSS selector must exist in styles.css."""
        css = read_css()
        assert ".file-tab-bar" in css, ".file-tab-bar selector not found in styles.css"

    def test_file_tab_selector_exists(self):
        """.file-tab { pattern must exist as a distinct selector in styles.css."""
        css = read_css()
        assert re.search(r"\.file-tab\s*\{", css), (
            ".file-tab { pattern not found in styles.css"
        )

    def test_file_tab_active_selector_exists(self):
        """.file-tab.active selector must exist in styles.css."""
        css = read_css()
        assert ".file-tab.active" in css, (
            ".file-tab.active selector not found in styles.css"
        )

    def test_file_tab_dirty_selector_exists(self):
        """.file-tab-dirty selector must exist in styles.css."""
        css = read_css()
        assert ".file-tab-dirty" in css, (
            ".file-tab-dirty selector not found in styles.css"
        )

    def test_file_tab_close_selector_exists(self):
        """.file-tab-close selector must exist in styles.css."""
        css = read_css()
        assert ".file-tab-close" in css, (
            ".file-tab-close selector not found in styles.css"
        )

    def test_file_tab_pin_selector_exists(self):
        """.file-tab-pin selector must exist in styles.css."""
        css = read_css()
        assert ".file-tab-pin" in css, ".file-tab-pin selector not found in styles.css"

    def test_uses_design_tokens_accent_and_bg_primary(self):
        """Tab bar CSS must use var(--accent) and var(--bg-primary) design tokens."""
        css = read_css()
        # Find the tab bar section
        tab_bar_idx = css.find(".file-tab-bar")
        assert tab_bar_idx != -1, ".file-tab-bar not found in styles.css"
        # The tab bar CSS block must use design tokens
        tab_bar_section = css[tab_bar_idx : tab_bar_idx + TAB_BAR_SECTION_LOOKAHEAD]
        assert "var(--accent)" in tab_bar_section, (
            "var(--accent) design token not used in .file-tab-bar CSS block"
        )
        assert "var(--bg-primary)" in tab_bar_section, (
            "var(--bg-primary) design token not used in .file-tab-bar CSS block"
        )

    def test_active_tab_uses_accent_color(self):
        """The .file-tab.active rule must use var(--accent) for background."""
        css = read_css()
        active_idx = css.find(".file-tab.active")
        assert active_idx != -1, ".file-tab.active not found in styles.css"
        # Extract the rule block after the selector
        rule_start = css.find("{", active_idx)
        rule_end = css.find("}", rule_start)
        assert rule_start != -1 and rule_end != -1, (
            ".file-tab.active rule block not found"
        )
        rule_block = css[rule_start : rule_end + 1]
        assert "var(--accent)" in rule_block, (
            "var(--accent) not used in .file-tab.active rule block"
        )

    def test_dirty_indicator_has_border_radius(self):
        """.file-tab-dirty must have border-radius for circular dot pattern."""
        css = read_css()
        dirty_idx = css.find(".file-tab-dirty")
        assert dirty_idx != -1, ".file-tab-dirty not found in styles.css"
        # Extract the rule block after the selector
        rule_start = css.find("{", dirty_idx)
        rule_end = css.find("}", rule_start)
        assert rule_start != -1 and rule_end != -1, (
            ".file-tab-dirty rule block not found"
        )
        rule_block = css[rule_start : rule_end + 1]
        assert "border-radius" in rule_block, (
            "border-radius not found in .file-tab-dirty rule — must be circular (50%)"
        )
