"""Behavioral regression tests for markdown preprocessing.

The markdown preprocessor lives in static/js/lib/preprocess-markdown.js so it can be
executed with real inputs here (via Node) instead of being scanned for source patterns.

It handles two transformations:
1. stripFrontmatter() - Extract YAML frontmatter from the start of files
2. transformWikilinks() - Convert Obsidian [[wikilinks]] to markdown links
3. renderFrontmatter() - Render frontmatter as HTML for display

Browser-level rendering coverage lives in the reality-check acceptance suite.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
PREPROCESS_JS = STATIC_DIR / "js" / "lib" / "preprocess-markdown.js"

NODE = shutil.which("node")

requires_node = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the JS preprocess-markdown module"
)


def _strip_frontmatter(markdown_source: str) -> dict:
    """Execute stripFrontmatter() from preprocess-markdown.js in Node and return result."""
    assert NODE is not None  # guarded by requires_node
    module_url = PREPROCESS_JS.resolve().as_uri()
    script = (
        f"import {{ stripFrontmatter }} from {json.dumps(module_url)};\n"
        f"const input = {json.dumps(markdown_source)};\n"
        f"const result = stripFrontmatter(input);\n"
        f"process.stdout.write(JSON.stringify(result));"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _transform_wikilinks(markdown_source: str) -> str:
    """Execute transformWikilinks() from preprocess-markdown.js in Node and return result."""
    assert NODE is not None  # guarded by requires_node
    module_url = PREPROCESS_JS.resolve().as_uri()
    script = (
        f"import {{ transformWikilinks }} from {json.dumps(module_url)};\n"
        f"const input = {json.dumps(markdown_source)};\n"
        f"process.stdout.write(transformWikilinks(input));"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _render_frontmatter(frontmatter: str) -> str:
    """Execute renderFrontmatter() from preprocess-markdown.js in Node and return result."""
    assert NODE is not None  # guarded by requires_node
    module_url = PREPROCESS_JS.resolve().as_uri()
    script = (
        f"import {{ renderFrontmatter }} from {json.dumps(module_url)};\n"
        f"const input = {json.dumps(frontmatter)};\n"
        f"process.stdout.write(renderFrontmatter(input));"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@requires_node
class TestStripFrontmatter:
    """Test YAML frontmatter extraction."""

    def test_frontmatter_at_start_is_extracted(self):
        """Frontmatter starting at offset 0 is extracted and removed from body."""
        source = "---\ntitle: Test\nauthor: Alice\n---\n# Content\n\nBody text."
        result = _strip_frontmatter(source)
        assert result["frontmatter"] == "title: Test\nauthor: Alice"
        assert result["body"] == "# Content\n\nBody text."

    def test_no_frontmatter_returns_null_and_full_body(self):
        """Files without frontmatter return null frontmatter and unchanged body."""
        source = "# Just a heading\n\nSome content."
        result = _strip_frontmatter(source)
        assert result["frontmatter"] is None
        assert result["body"] == source

    def test_mid_document_thematic_break_is_preserved(self):
        """A --- thematic break in the middle of a document is NOT treated as frontmatter."""
        source = "# Title\n\nSome text.\n\n---\n\nMore text."
        result = _strip_frontmatter(source)
        assert result["frontmatter"] is None
        assert result["body"] == source

    def test_frontmatter_with_windows_line_endings(self):
        """Frontmatter with \\r\\n line endings is handled correctly."""
        source = "---\r\ntitle: Windows Test\r\n---\r\n# Content"
        result = _strip_frontmatter(source)
        assert result["frontmatter"] == "title: Windows Test"
        assert result["body"] == "# Content"

    def test_frontmatter_with_mixed_line_endings(self):
        """Frontmatter with mixed \\r\\n and \\n is handled."""
        source = "---\r\ntitle: Mixed\nauthor: Bob\r\n---\nContent"
        result = _strip_frontmatter(source)
        assert result["frontmatter"] == "title: Mixed\nauthor: Bob"
        assert result["body"] == "Content"

    def test_empty_frontmatter_block(self):
        """An empty frontmatter block (---\\n---) is extracted as empty string."""
        source = "---\n---\n# Content"
        result = _strip_frontmatter(source)
        assert result["frontmatter"] == ""
        assert result["body"] == "# Content"

    def test_frontmatter_with_multiline_values(self):
        """Frontmatter with multiline YAML values is preserved."""
        source = "---\ntitle: Test\ndescription: |\n  A long description\n  spanning multiple lines\n---\nBody"
        result = _strip_frontmatter(source)
        assert "description: |" in result["frontmatter"]
        assert "spanning multiple lines" in result["frontmatter"]
        assert result["body"] == "Body"

    def test_frontmatter_stops_at_first_closing_delimiter(self):
        """Non-greedy matching stops at the first closing ---, not later ones."""
        source = "---\ntitle: Test\n---\nBody\n\n---\n\nMore content"
        result = _strip_frontmatter(source)
        assert result["frontmatter"] == "title: Test"
        assert result["body"] == "Body\n\n---\n\nMore content"

    def test_incomplete_frontmatter_is_not_matched(self):
        """A frontmatter block missing the closing --- is not extracted."""
        source = "---\ntitle: Incomplete\n# Content"
        result = _strip_frontmatter(source)
        assert result["frontmatter"] is None
        assert result["body"] == source

    def test_empty_string_returns_null_frontmatter(self):
        """An empty input string returns null frontmatter and empty body."""
        result = _strip_frontmatter("")
        assert result["frontmatter"] is None
        assert result["body"] == ""


@requires_node
class TestTransformWikilinks:
    """Test Obsidian wikilink transformation."""

    def test_simple_wikilink_without_pipe(self):
        """[[target]] is converted to [target](target.md)."""
        source = "See [[some-page]] for details."
        result = _transform_wikilinks(source)
        assert result == "See [some-page](some-page.md) for details."

    def test_wikilink_with_display_text(self):
        """[[target|display]] is converted to [display](target.md)."""
        source = "Check out [[some-slug|This Page]] here."
        result = _transform_wikilinks(source)
        assert result == "Check out [This Page](some-slug.md) here."

    def test_multiple_wikilinks_in_text(self):
        """Multiple wikilinks are all transformed."""
        source = "See [[page-one]] and [[page-two|Second Page]]."
        result = _transform_wikilinks(source)
        assert result == "See [page-one](page-one.md) and [Second Page](page-two.md)."

    def test_wikilink_with_spaces_in_target(self):
        """Wikilinks can have spaces in the target (though not typical)."""
        source = "Link to [[my page]] here."
        result = _transform_wikilinks(source)
        assert result == "Link to [my page](my page.md) here."

    def test_wikilink_with_hyphens_and_underscores(self):
        """Wikilinks with hyphens and underscores are handled."""
        source = "See [[my-page_v2]]."
        result = _transform_wikilinks(source)
        assert result == "See [my-page_v2](my-page_v2.md)."

    def test_wikilink_at_start_of_line(self):
        """Wikilinks at the start of a line are transformed."""
        source = "[[intro]] is the first page."
        result = _transform_wikilinks(source)
        assert result == "[intro](intro.md) is the first page."

    def test_wikilink_at_end_of_line(self):
        """Wikilinks at the end of a line are transformed."""
        source = "Go to [[conclusion]]"
        result = _transform_wikilinks(source)
        assert result == "Go to [conclusion](conclusion.md)"

    def test_nested_brackets_are_not_matched(self):
        """Nested brackets should not break the regex (edge case)."""
        # This is a malformed wikilink, but we should handle it gracefully
        source = "Text with [[outer|[inner]]] here."
        # The regex should match [[outer|[inner]]]
        result = _transform_wikilinks(source)
        # Expected: [inner]](outer.md) - the pipe splits at the first |
        assert "[inner]]](outer.md)" in result or "[[outer|[inner]]]" in result

    def test_empty_string_returns_empty(self):
        """An empty input string returns an empty output."""
        assert _transform_wikilinks("") == ""

    def test_text_without_wikilinks_is_unchanged(self):
        """Text with no wikilinks is returned unchanged."""
        source = "This is plain text with [normal](link.md) links."
        result = _transform_wikilinks(source)
        assert result == source

    def test_wikilink_with_pipe_in_display_text(self):
        """A pipe character in the display text should only split at the first pipe."""
        # This is an edge case - the regex splits on the first |
        source = "See [[target|Display | Text]]."
        result = _transform_wikilinks(source)
        # The first | is the separator, so "Display | Text" is the display
        assert result == "See [Display | Text]](target.md)."

    def test_wikilink_with_special_chars_in_display(self):
        """Display text can contain special characters."""
        source = "Read [[guide|User's Guide & FAQ]]."
        result = _transform_wikilinks(source)
        assert result == "Read [User's Guide & FAQ](guide.md)."

    def test_multiple_pipes_uses_first_as_separator(self):
        """When there are multiple pipes, the first one is the target/display separator."""
        source = "[[a|b|c]]"
        result = _transform_wikilinks(source)
        # First regex matches [[a|b]] with target=a, display=b, leaving |c]]
        # Actually, the regex is non-greedy on the target side, so it should match correctly
        # Let's check: [[a|b|c]] - target is "a", display is "b|c" (everything after first |)
        # Wait, the regex is /\[\[([^\]|]+)\|([^\]]+)\]\]/g
        # [^\]|]+ means "not ] or |", so target stops at first |
        # [^\]]+ means "not ]", so display can contain |
        assert result == "[b|c](a.md)"


@requires_node
class TestRenderFrontmatter:
    """Test frontmatter HTML rendering."""

    def test_null_frontmatter_returns_empty_string(self):
        """Null or empty frontmatter returns an empty string."""
        assert _render_frontmatter("") == ""

    def test_frontmatter_is_rendered_as_html(self):
        """Valid frontmatter is rendered as an HTML panel."""
        frontmatter = "title: Test\nauthor: Alice"
        result = _render_frontmatter(frontmatter)
        assert '<div class="frontmatter-panel">' in result
        assert '<div class="frontmatter-header">Document Metadata</div>' in result
        assert '<pre class="frontmatter-content">' in result
        assert "title: Test" in result
        assert "author: Alice" in result

    def test_html_in_frontmatter_is_escaped(self):
        """HTML special characters in frontmatter are escaped to prevent XSS."""
        frontmatter = 'title: <script>alert("xss")</script>'
        result = _render_frontmatter(frontmatter)
        assert "&lt;script&gt;" in result
        assert "&lt;/script&gt;" in result
        assert "<script>" not in result

    def test_ampersands_are_escaped(self):
        """Ampersands in frontmatter are escaped."""
        frontmatter = "company: Smith & Co"
        result = _render_frontmatter(frontmatter)
        assert "Smith &amp; Co" in result
        assert "Smith & Co" not in result or "&amp;" in result

    def test_quotes_are_escaped(self):
        """Quotes in frontmatter are escaped."""
        frontmatter = 'title: "Quoted Title"'
        result = _render_frontmatter(frontmatter)
        assert "&quot;" in result or "&#39;" in result

    def test_multiline_frontmatter_preserves_structure(self):
        """Multiline YAML frontmatter preserves line breaks in the HTML."""
        frontmatter = "title: Test\ndescription: |\n  Line 1\n  Line 2"
        result = _render_frontmatter(frontmatter)
        # The <pre> tag should preserve whitespace
        assert "Line 1" in result
        assert "Line 2" in result


class TestPreprocessModule:
    """Test that the preprocess-markdown.js module exists and exports functions."""

    def test_module_exists(self):
        assert PREPROCESS_JS.exists(), "static/js/lib/preprocess-markdown.js is missing"

    def test_module_exports_strip_frontmatter(self):
        content = PREPROCESS_JS.read_text()
        assert "export function stripFrontmatter" in content

    def test_module_exports_transform_wikilinks(self):
        content = PREPROCESS_JS.read_text()
        assert "export function transformWikilinks" in content

    def test_module_exports_render_frontmatter(self):
        content = PREPROCESS_JS.read_text()
        assert "export function renderFrontmatter" in content


@requires_node
class TestIntegration:
    """Test the full preprocessing pipeline (frontmatter + wikilinks)."""

    def test_file_with_frontmatter_and_wikilinks(self):
        """A file with both frontmatter and wikilinks is processed correctly."""
        source = "---\ntitle: My Note\n---\n# Content\n\nSee [[other-page]] for more."
        
        # Strip frontmatter first
        result = _strip_frontmatter(source)
        assert result["frontmatter"] == "title: My Note"
        
        # Transform wikilinks in the body
        body_with_links = _transform_wikilinks(result["body"])
        assert body_with_links == "# Content\n\nSee [other-page](other-page.md) for more."

    def test_file_without_frontmatter_but_with_wikilinks(self):
        """A file with wikilinks but no frontmatter is processed correctly."""
        source = "# Title\n\nCheck [[link-one]] and [[link-two|Link Two]]."
        
        result = _strip_frontmatter(source)
        assert result["frontmatter"] is None
        
        body_with_links = _transform_wikilinks(result["body"])
        assert "[link-one](link-one.md)" in body_with_links
        assert "[Link Two](link-two.md)" in body_with_links

    def test_file_with_frontmatter_but_no_wikilinks(self):
        """A file with frontmatter but no wikilinks is processed correctly."""
        source = "---\ntitle: Test\n---\n# Content\n\nNormal [link](page.md)."
        
        result = _strip_frontmatter(source)
        assert result["frontmatter"] == "title: Test"
        
        body_with_links = _transform_wikilinks(result["body"])
        assert body_with_links == "# Content\n\nNormal [link](page.md)."

    def test_empty_file(self):
        """An empty file is handled gracefully."""
        source = ""
        
        result = _strip_frontmatter(source)
        assert result["frontmatter"] is None
        assert result["body"] == ""
        
        body_with_links = _transform_wikilinks(result["body"])
        assert body_with_links == ""
