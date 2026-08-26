"""Behavioral regression tests for the Markdown image source rewriter.

The rewriter lives in static/js/lib/rewrite-image-src.js so it can be executed
with real inputs here (via Node) instead of being scanned for source patterns.

It resolves relative Markdown image sources to authenticated
`/api/files/content?path=<encoded path>` URLs, given the path of the current
Markdown file, and leaves absolute/non-file sources (http:, https:,
protocol-relative //, data:) untouched.

Browser-level rendering coverage lives in the reality-check acceptance suite;
this file only covers the pure path-resolution/URL-construction logic.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
REWRITER_JS = STATIC_DIR / "js" / "lib" / "rewrite-image-src.js"

NODE = shutil.which("node")

requires_node = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the JS rewrite-image-src module"
)


def _rewrite_image_src(current_file: str, image_source: str) -> str:
    """Execute rewriteImageSrc() from rewrite-image-src.js in Node and return result."""
    assert NODE is not None  # guarded by requires_node
    module_url = REWRITER_JS.resolve().as_uri()
    script = (
        f"import {{ rewriteImageSrc }} from {json.dumps(module_url)};\n"
        f"const currentFile = {json.dumps(current_file)};\n"
        f"const imageSource = {json.dumps(image_source)};\n"
        f"process.stdout.write(rewriteImageSrc(currentFile, imageSource));"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@requires_node
class TestRelativeResolution:
    """AC-1: relative image sources resolve to /api/files/content URLs."""

    def test_simple_relative_path(self):
        result = _rewrite_image_src("docs/page.md", "img/x.png")
        assert result == "/api/files/content?path=docs%2Fimg%2Fx.png"

    def test_dot_slash_prefix(self):
        result = _rewrite_image_src("docs/page.md", "./img/x.png")
        assert result == "/api/files/content?path=docs%2Fimg%2Fx.png"

    def test_root_level_file(self):
        result = _rewrite_image_src("README.md", "logo.png")
        assert result == "/api/files/content?path=logo.png"

    def test_root_level_file_real_repo_path(self):
        result = _rewrite_image_src(
            "README.md", "assets/branding/icons/filebrowser-icon-128.png"
        )
        assert (
            result
            == "/api/files/content?path=assets%2Fbranding%2Ficons%2Ffilebrowser-icon-128.png"
        )

    def test_space_in_filename_is_encoded(self):
        result = _rewrite_image_src("docs/page.md", "img/test image.png")
        assert result == "/api/files/content?path=docs%2Fimg%2Ftest%20image.png"

    def test_nested_subdirectories(self):
        result = _rewrite_image_src("a/b/c/d/file.md", "e/f/g/image.png")
        assert result == "/api/files/content?path=a%2Fb%2Fc%2Fd%2Fe%2Ff%2Fg%2Fimage.png"


@requires_node
class TestAbsolutePassthrough:
    """AC-2: absolute/non-file sources pass through byte-for-byte unchanged."""

    def test_http_url_unchanged(self):
        url = "http://example.com/image.png"
        assert _rewrite_image_src("any/file.md", url) == url

    def test_https_url_unchanged(self):
        url = "https://cdn.example.com/img.jpg"
        assert _rewrite_image_src("any/file.md", url) == url

    def test_protocol_relative_url_unchanged(self):
        url = "//cdn.example.com/img.jpg"
        assert _rewrite_image_src("docs/page.md", url) == url

    def test_data_uri_unchanged(self):
        uri = "data:image/png;base64,iVBORw0KGgo="
        assert _rewrite_image_src("any/file.md", uri) == uri

    def test_absolute_url_unaffected_by_current_file(self):
        url = "https://example.com/img.png"
        result_a = _rewrite_image_src("a/b/c.md", url)
        result_b = _rewrite_image_src("x/y/z.md", url)
        assert result_a == url
        assert result_b == url


@requires_node
class TestParentSegmentResolution:
    """AC-3: '..' segments resolve fully, with no '..' left in the output."""

    def test_single_parent_segment(self):
        result = _rewrite_image_src("docs/page.md", "../assets/y.png")
        assert result == "/api/files/content?path=assets%2Fy.png"
        assert ".." not in result

    def test_multiple_parent_segments(self):
        result = _rewrite_image_src("docs/sub/deep.md", "../../assets/logo.png")
        assert result == "/api/files/content?path=assets%2Flogo.png"
        assert ".." not in result

    def test_mixed_dot_slash_and_parent_segments(self):
        result = _rewrite_image_src("docs/page.md", "./../assets/y.png")
        assert result == "/api/files/content?path=assets%2Fy.png"
        assert ".." not in result

    def test_interleaved_parent_and_regular_segments(self):
        result = _rewrite_image_src("p/q/r.md", "../s/../t/u.png")
        assert result == "/api/files/content?path=p%2Ft%2Fu.png"
        assert ".." not in result


class TestModuleShape:
    """Test that the rewriter module exists and exports the expected function."""

    def test_module_exists(self):
        assert REWRITER_JS.exists(), "static/js/lib/rewrite-image-src.js is missing"

    def test_module_exports_rewrite_image_src(self):
        content = REWRITER_JS.read_text()
        assert "export function rewriteImageSrc" in content
