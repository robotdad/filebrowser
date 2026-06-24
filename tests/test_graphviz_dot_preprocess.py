"""Behavioral regression tests for DOT namespaced-attribute preprocessing.

The DOT preprocessor lives in the pure module static/js/lib/preprocess-dot.js so it
can be executed with real inputs here (via Node) instead of being scanned for source
patterns. preprocessDot() quotes unquoted dotted attribute keys (param.owner=...) so
Graphviz can parse them, while leaving dotted text that appears inside quoted string
values (e.g. label="emit metric.count=3") untouched -- the previous regex corrupted
those, which is the bug this suite guards against.

Browser-level rendering coverage lives in the reality-check acceptance suite.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
PREPROCESS_JS = STATIC_DIR / "js" / "lib" / "preprocess-dot.js"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "diagrams"

NODE = shutil.which("node")

requires_node = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the JS preprocess-dot module"
)


def _preprocess(dot_source: str) -> str:
    """Execute preprocessDot() from preprocess-dot.js in Node and return the result."""
    assert NODE is not None  # guarded by requires_node
    module_url = PREPROCESS_JS.resolve().as_uri()
    script = (
        f"import {{ preprocessDot }} from {json.dumps(module_url)};\n"
        f"const input = {json.dumps(dot_source)};\n"
        f"process.stdout.write(preprocessDot(input));"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@requires_node
class TestPreprocessDot:
    def test_unquoted_dotted_key_gets_quoted(self):
        assert _preprocess('param.owner="alice"') == '"param.owner"="alice"'

    def test_already_quoted_key_is_unchanged(self):
        src = '"param.owner"="alice"'
        assert _preprocess(src) == src

    def test_dotted_token_inside_quoted_value_is_preserved(self):
        """The bug case: a dotted token + '=' inside a quoted string must NOT be rewritten."""
        src = 'Work [label="emit metric.count=3"]'
        assert _preprocess(src) == src

    def test_dotted_token_inside_quoted_label_with_spaces(self):
        src = 'End -> Stop [label="route a.b=c here"]'
        assert _preprocess(src) == src

    def test_nested_three_level_key_gets_quoted_whole(self):
        assert _preprocess('param.owner.deep="x"') == '"param.owner.deep"="x"'

    def test_numeric_dotted_value_is_unchanged(self):
        # First char of a quotable key must be a letter/underscore, so 1.5 is left alone.
        assert _preprocess("width=1.5") == "width=1.5"

    def test_dotted_node_reference_without_assignment_is_unchanged(self):
        assert _preprocess("a.b -> c.d;") == "a.b -> c.d;"

    def test_plain_keys_are_unchanged(self):
        assert _preprocess("rankdir=LR shape=box") == "rankdir=LR shape=box"

    def test_empty_source_returns_empty(self):
        assert _preprocess("") == ""

    def test_multiple_keys_on_one_line(self):
        src = "graph [ param.owner=\"o\", param.count=\"c\" ]"
        expected = 'graph [ "param.owner"="o", "param.count"="c" ]'
        assert _preprocess(src) == expected


@requires_node
class TestNamespacedFixtureRoundTrip:
    """Run the actual committed fixture through preprocessDot and assert correctness."""

    def test_fixture_keys_quoted_and_label_preserved(self):
        fixture = FIXTURES_DIR / "namespaced-attrs.dot"
        out = _preprocess(fixture.read_text())
        # Namespaced KEYS are quoted so Graphviz will accept them.
        assert '"param.owner"=' in out
        assert '"context.route"=' in out
        # The dotted token inside the quoted LABEL value is preserved verbatim.
        assert 'label="emit metric.count=3"' in out
        # ...and is NOT corrupted into a broken/quoted form.
        assert '"metric.count"' not in out


class TestPreprocessModule:
    def test_module_exists_and_exports_function(self):
        assert PREPROCESS_JS.exists(), "static/js/lib/preprocess-dot.js is missing"
        assert "export function preprocessDot" in PREPROCESS_JS.read_text()


class TestNamespacedAttrsFixture:
    def test_fixture_file_exists(self):
        assert (FIXTURES_DIR / "namespaced-attrs.dot").exists()

    def test_fixture_contains_namespaced_key_and_dotted_label(self):
        content = (FIXTURES_DIR / "namespaced-attrs.dot").read_text()
        # An unquoted namespaced attribute key (the feature) ...
        assert "param.owner=" in content
        # ... and a dotted token inside a quoted label (the regression case).
        assert 'label="emit metric.count=3"' in content
