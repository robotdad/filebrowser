"""Static regression tests for DOT namespaced attribute preprocessing.

These tests verify that the preprocessDot function is present and called
on both rendering paths, ensuring DOT files with dotted attribute keys
(e.g., param.owner, context.route) can be parsed successfully.
"""

import re
from functools import lru_cache
from pathlib import Path

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
PREVIEW_JS = STATIC_DIR / "js" / "components" / "preview.js"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "diagrams"


@lru_cache(maxsize=1)
def read_preview() -> str:
    return PREVIEW_JS.read_text()


class TestPreprocessDotFunction:
    def test_preprocess_dot_function_defined(self):
        """preprocessDot function must be defined in preview.js."""
        preview = read_preview()
        assert "function preprocessDot(" in preview, (
            "preprocessDot function not found in preview.js"
        )

    def test_preprocess_dot_has_regex_replacement(self):
        """preprocessDot must use regex to quote dotted attribute keys."""
        preview = read_preview()
        # Check that the function contains a regex replace operation
        assert re.search(
            r"function preprocessDot\([^)]*\)\s*{[^}]*\.replace\([^)]*\)",
            preview,
            re.DOTALL
        ), (
            "preprocessDot function must contain a .replace() call"
        )


class TestGraphTabRenderingPath:
    def test_graph_tab_uses_preprocess_dot(self):
        """Graph tab (d3-graphviz) must call preprocessDot before renderDot."""
        preview = read_preview()
        # Find the renderDot call and verify it's wrapped with preprocessDot
        assert re.search(
            r"renderer\.renderDot\(\s*preprocessDot\(",
            preview
        ), (
            "Graph tab rendering path must call renderDot(preprocessDot(text))"
        )


class TestEditTabRenderingPath:
    def test_edit_tab_uses_preprocess_dot(self):
        """Edit tab (hpcc-wasm) must call preprocessDot before layout."""
        preview = read_preview()
        # Find the hpccGraphviz.layout call and verify it uses preprocessDot
        assert re.search(
            r"hpccGraphviz\.layout\(\s*preprocessDot\(",
            preview
        ), (
            "Edit tab rendering path must call layout(preprocessDot(editText), ...)"
        )


class TestNamespacedAttrsFixture:
    def test_fixture_file_exists(self):
        """Namespaced attributes fixture must exist."""
        fixture_path = FIXTURES_DIR / "namespaced-attrs.dot"
        assert fixture_path.exists(), (
            f"Fixture file {fixture_path} does not exist"
        )

    def test_fixture_contains_dotted_attributes(self):
        """Fixture must contain actual dotted attribute keys."""
        fixture_path = FIXTURES_DIR / "namespaced-attrs.dot"
        if not fixture_path.exists():
            # Skip if fixture doesn't exist (will be caught by other test)
            return
        
        content = fixture_path.read_text()
        # Check for at least one dotted attribute key
        assert re.search(r'[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\s*=', content), (
            "Fixture must contain at least one dotted attribute key (e.g., param.owner=)"
        )
