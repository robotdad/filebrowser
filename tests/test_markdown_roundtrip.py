"""Executable safeguards for Markdown rich-editor serialization.

The helper deliberately has no Tiptap dependency so these tests can run its
exact byte comparison against representative serializer outputs in Node.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROUNDTRIP_JS = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "lib"
    / "markdown-roundtrip.js"
)
NODE = shutil.which("node")
requires_node = pytest.mark.skipif(
    NODE is None, reason="node is required to execute markdown-roundtrip.js"
)


def _run_helper(original: str, serialized: str) -> dict:
    """Run the pure helper with a fake serializer result."""
    assert NODE is not None
    module_url = ROUNDTRIP_JS.resolve().as_uri()
    script = (
        "import { matchesMarkdownIgnoringTrailingLfs, restoreOriginalTrailingLfs } "
        f"from {json.dumps(module_url)};\n"
        f"const original = {json.dumps(original)};\n"
        f"const fakeSerializer = () => {json.dumps(serialized)};\n"
        "const candidate = fakeSerializer();\n"
        "process.stdout.write(JSON.stringify({"
        "safe: matchesMarkdownIgnoringTrailingLfs(original, candidate),"
        "restored: restoreOriginalTrailingLfs(original, candidate)"
        "}));"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@requires_node
class TestMarkdownRoundtrip:
    def test_accepts_only_trailing_lf_difference(self):
        result = _run_helper("# Heading\n\n", "# Heading")
        assert result["safe"] is True
        assert result["restored"] == "# Heading\n\n"

    def test_preserves_original_lf_suffix_not_serializer_suffix(self):
        result = _run_helper("content\n\n", "changed\n\n\n")
        assert result["safe"] is False
        assert result["restored"] == "changed\n\n"

    def test_does_not_ignore_spaces_or_carriage_returns(self):
        assert _run_helper("line \n", "line\n")["safe"] is False
        assert _run_helper("line\r\n", "line\n")["safe"] is False

    @pytest.mark.parametrize(
        ("original", "serialized"),
        [
            (
                "![Sample Logo](logo.svg)",
                "",
            ),
            (
                "```python\ndef calculate_total(items):\n    return sum(item.price for item in items)\n```",
                "`def calculate_total(items):`\\\n`    return sum(item.price for item in items)`",
            ),
            (
                "| Product | Quantity | Price |\n| :--- | :--- | :--- |\n| Widget A | 10 | $5.00 |",
                "ProductQuantityPriceWidget A10$5.00Gadget B2$15.50",
            ),
            (
                "- [x] Initial review complete\n- [ ] Pending deployment signoff",
                "- \\[x\\] Initial review complete\n- \\[ \\] Pending deployment signoff",
            ),
        ],
        ids=["image", "fenced-code", "table", "task-list"],
    )
    def test_blocks_each_baseline_loss(self, original, serialized):
        assert _run_helper(original, serialized)["safe"] is False

    @pytest.mark.parametrize(
        ("original", "serialized"),
        [
            ("---\ntitle: a\n---\n", "title: a\n"),
            ("<details>\nsummary\n</details>", "summary"),
            ("[ref]: https://example.test\n\nUse [ref].", "Use [ref](https://example.test)."),
            ("*emphasis*\n", "_emphasis_\n"),
            ("unknown \u2060 format", "unknown format"),
        ],
        ids=["frontmatter", "html", "reference-definition", "format-variant", "unknown-character"],
    )
    def test_blocks_unknown_or_normalized_markdown_variants(self, original, serialized):
        assert _run_helper(original, serialized)["safe"] is False


def test_component_wires_preflight_before_publishing_editor():
    """Keep the component flow aligned with the pure runtime guard."""
    source = (
        Path(__file__).parent.parent
        / "filebrowser"
        / "static"
        / "js"
        / "components"
        / "wysiwyg-editor.js"
    ).read_text()
    assert "editable: false" in source
    assert "matchesMarkdownIgnoringTrailingLfs(original, serialized)" in source
    assert source.index("matchesMarkdownIgnoringTrailingLfs(original, serialized)") < source.index(
        "editor.setEditable(true)"
    )
    assert source.index("matchesMarkdownIgnoringTrailingLfs(original, serialized)") < source.index(
        "onEditorReady?.(editor)"
    )