"""Static regression tests for preview XSS mitigations (review fix A).

These tests verify that the expected security controls are present in the
static source files and serve as a guard against accidental regression.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
PREVIEW_JS = STATIC_DIR / "js" / "components" / "preview.js"
INDEX_HTML = STATIC_DIR / "index.html"


@lru_cache(maxsize=1)
def read_preview() -> str:
    return PREVIEW_JS.read_text()


@lru_cache(maxsize=1)
def read_html() -> str:
    return INDEX_HTML.read_text()


class TestMarkdownSanitization:
    def test_dompurify_imported(self):
        """preview.js must import DOMPurify."""
        assert "import DOMPurify from 'dompurify'" in read_preview(), (
            "DOMPurify import not found in preview.js"
        )

    def test_dompurify_sanitize_used(self):
        """preview.js must call DOMPurify.sanitize() on the marked output."""
        assert "DOMPurify.sanitize(" in read_preview(), (
            "DOMPurify.sanitize() call not found in preview.js"
        )

    def test_sanitize_wraps_marked_parse(self):
        """DOMPurify.sanitize must wrap marked.parse, not replace it."""
        preview = read_preview()
        assert re.search(r"DOMPurify\.sanitize\(.*marked\.parse\(", preview), (
            "Expected DOMPurify.sanitize(marked.parse(...)) pattern not found"
        )


class TestHtmlIframeSandbox:
    def test_html_preview_iframe_has_sandbox(self):
        """The HTML preview iframe must include the sandbox attribute."""
        assert 'sandbox=""' in read_preview(), (
            'html-preview-frame iframe is missing sandbox="" attribute in preview.js'
        )

    def test_html_preview_iframe_sandbox_is_empty(self):
        """The sandbox attribute must be empty (deny all capabilities)."""
        preview = read_preview()
        # Match the iframe element with the html-preview-frame class
        match = re.search(r'html-preview-frame[^`]*?sandbox="([^"]*)"', preview)
        assert match, "html-preview-frame iframe with sandbox attribute not found"
        assert match.group(1) == "", (
            f"sandbox attribute should be empty but got: '{match.group(1)}'"
        )


class TestImportMapDomPurify:
    def _extract_importmap_json(self) -> dict:
        html = read_html()
        match = re.search(r'<script type="importmap">(.*?)</script>', html, re.DOTALL)
        assert match, "No importmap script tag found in index.html"
        return json.loads(match.group(1).strip())

    def test_dompurify_entry_in_importmap(self):
        """importmap must contain a dompurify entry."""
        parsed = self._extract_importmap_json()
        imports = parsed.get("imports", {})
        assert "dompurify" in imports, (
            "'dompurify' entry missing from importmap imports in index.html"
        )

    def test_dompurify_points_to_esm_sh(self):
        """dompurify importmap entry must point to esm.sh."""
        parsed = self._extract_importmap_json()
        url = parsed.get("imports", {}).get("dompurify", "")
        assert url.startswith("https://esm.sh/dompurify"), (
            f"dompurify importmap URL does not start with https://esm.sh/dompurify: {url}"
        )

    def test_importmap_still_valid_json(self):
        """importmap must remain valid JSON after adding dompurify."""
        parsed = self._extract_importmap_json()
        assert "imports" in parsed
        # Verify all previously-required entries are still present
        for key in ("preact", "preact/hooks", "htm", "marked"):
            assert key in parsed["imports"], f"'{key}' missing from importmap"
