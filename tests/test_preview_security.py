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
MARKDOWN_EDITOR_JS = STATIC_DIR / "js" / "components" / "markdown-editor.js"
INDEX_HTML = STATIC_DIR / "index.html"


@lru_cache(maxsize=1)
def read_preview() -> str:
    return PREVIEW_JS.read_text()


@lru_cache(maxsize=1)
def read_markdown_editor() -> str:
    return MARKDOWN_EDITOR_JS.read_text()


@lru_cache(maxsize=1)
def read_html() -> str:
    return INDEX_HTML.read_text()


class TestMarkdownSanitization:
    """Markdown rendering and sanitization live in markdown-editor.js.

    They were moved there from preview.js when MarkdownEditor was introduced
    (commit 0da3877); these assertions follow the code to its current home
    rather than scanning the file it used to live in.
    """

    def test_dompurify_imported(self):
        """markdown-editor.js must import DOMPurify."""
        assert "import DOMPurify from 'dompurify'" in read_markdown_editor(), (
            "DOMPurify import not found in markdown-editor.js"
        )

    def test_dompurify_sanitize_used(self):
        """markdown-editor.js must call DOMPurify.sanitize()."""
        assert "DOMPurify.sanitize(" in read_markdown_editor(), (
            "DOMPurify.sanitize() call not found in markdown-editor.js"
        )

    def test_sanitize_wraps_marked_parse(self):
        """The marked.parse() output must flow through DOMPurify.sanitize().

        marked.parse() result is assigned to a local, and that local must be an
        argument to DOMPurify.sanitize() -- proving sanitization wraps the
        rendered markdown rather than replacing or bypassing it.
        """
        source = read_markdown_editor()

        parsed_var = re.search(r"(?:const|let|var)\s+(\w+)\s*=\s*marked\.parse\(", source)
        assert parsed_var, "No `<var> = marked.parse(...)` assignment found"
        var_name = parsed_var.group(1)

        sanitize_call = re.search(r"DOMPurify\.sanitize\(([^)]*)\)", source)
        assert sanitize_call, "No DOMPurify.sanitize(...) call found"

        assert var_name in sanitize_call.group(1), (
            f"marked.parse() output ({var_name!r}) is not passed to "
            f"DOMPurify.sanitize(); got: {sanitize_call.group(1)!r}"
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
