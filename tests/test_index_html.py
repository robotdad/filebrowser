"""Tests for xterm.js CDN imports in index.html (task-5-xterm-cdn-imports)."""

import json
import re
from functools import lru_cache
from pathlib import Path

INDEX_HTML = Path(__file__).parent.parent / "filebrowser" / "static" / "index.html"


@lru_cache(maxsize=1)
def read_html() -> str:
    return INDEX_HTML.read_text()


class TestXtermCSSLink:
    def test_xterm_css_link_present(self):
        """xterm.css CDN link must be present in <head>."""
        html = read_html()
        assert (
            'href="https://cdn.jsdelivr.net/npm/@xterm/xterm@6/css/xterm.min.css"'
            in html
        ), "xterm.css CDN link not found in index.html"

    def test_xterm_css_link_is_stylesheet(self):
        """The xterm CDN link must be a rel=stylesheet link."""
        html = read_html()
        assert (
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xterm/xterm@6/css/xterm.min.css">'
            in html
        ), "xterm CSS link must be a <link rel='stylesheet'> element"

    def test_xterm_css_link_before_importmap(self):
        """xterm CSS link must appear before the importmap script."""
        html = read_html()
        css_pos = html.find(
            'href="https://cdn.jsdelivr.net/npm/@xterm/xterm@6/css/xterm.min.css"'
        )
        importmap_pos = html.find('<script type="importmap">')
        assert css_pos != -1, "xterm CSS link not found"
        assert importmap_pos != -1, "importmap script not found"
        assert css_pos < importmap_pos, (
            "xterm CSS link must appear before <script type='importmap'>"
        )

    def test_xterm_css_link_after_main_styles(self):
        """xterm CSS link must appear after the main styles.css link."""
        html = read_html()
        styles_pos = html.find('href="/css/styles.css"')
        xterm_css_pos = html.find(
            'href="https://cdn.jsdelivr.net/npm/@xterm/xterm@6/css/xterm.min.css"'
        )
        assert styles_pos != -1, "main styles.css link not found"
        assert xterm_css_pos != -1, "xterm CSS link not found"
        assert xterm_css_pos > styles_pos, (
            "xterm CSS link must appear after the main styles.css link"
        )


class TestXtermImportMap:
    def _extract_importmap_json(self, html: str) -> str:
        """Extract the JSON content from the importmap script tag."""
        match = re.search(r'<script type="importmap">(.*?)</script>', html, re.DOTALL)
        assert match, "No importmap script tag found in index.html"
        return match.group(1).strip()

    def test_importmap_json_is_valid(self):
        """The importmap JSON must be valid (no trailing commas, etc.)."""
        html = read_html()
        raw_json = self._extract_importmap_json(html)
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"importmap JSON is invalid: {e}\nRaw JSON:\n{raw_json}"
            ) from e
        assert "imports" in parsed, "importmap JSON must have an 'imports' key"

    def test_xterm_xterm_entry_in_importmap(self):
        """Import map must contain @xterm/xterm entry."""
        html = read_html()
        raw_json = self._extract_importmap_json(html)
        parsed = json.loads(raw_json)
        imports = parsed.get("imports", {})
        assert "@xterm/xterm" in imports, "@xterm/xterm not found in importmap imports"
        assert imports["@xterm/xterm"] == "https://esm.sh/@xterm/xterm@6.0.0", (
            f"@xterm/xterm URL is wrong: {imports['@xterm/xterm']}"
        )

    def test_xterm_addon_fit_entry_in_importmap(self):
        """Import map must contain @xterm/addon-fit entry."""
        html = read_html()
        raw_json = self._extract_importmap_json(html)
        parsed = json.loads(raw_json)
        imports = parsed.get("imports", {})
        assert "@xterm/addon-fit" in imports, (
            "@xterm/addon-fit not found in importmap imports"
        )
        assert (
            imports["@xterm/addon-fit"] == "https://esm.sh/@xterm/addon-fit@0.11.0"
        ), f"@xterm/addon-fit URL is wrong: {imports['@xterm/addon-fit']}"

    def test_importmap_contains_all_required_entries(self):
        """Import map must contain all required entries: preact, preact/hooks, htm, marked, @xterm/xterm, @xterm/addon-fit, @codemirror/."""
        html = read_html()
        raw_json = self._extract_importmap_json(html)
        parsed = json.loads(raw_json)
        imports = parsed.get("imports", {})
        required_keys = [
            "preact",
            "preact/hooks",
            "htm",
            "marked",
            "@xterm/xterm",
            "@xterm/addon-fit",
            "@codemirror/",
        ]
        for key in required_keys:
            assert key in imports, f"'{key}' missing from importmap imports"
