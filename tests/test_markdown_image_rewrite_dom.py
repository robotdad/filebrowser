"""DOM-level test for the Markdown image-source rewriting in renderMarkdown.

renderMarkdown (in markdown-editor.js) sanitizes HTML with DOMPurify and then
walks every <img> element, passing each src through rewriteImageSrc().  This
test exercises the same DOM manipulation pattern -- using Node + jsdom -- to
prove:

  * Relative image sources are rewritten to /api/files/content?path=...
  * Absolute sources (http:, https:, //, data:) pass through byte-for-byte.

The test is intentionally independent of DOMPurify (which requires a CDN
import) and of the full Preact component tree.  It focuses only on the
DOM-mutation step that follows sanitization.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
REWRITER_JS = STATIC_DIR / "js" / "lib" / "rewrite-image-src.js"

NODE = shutil.which("node")


def _find_jsdom_cwd() -> Path | None:
    """Locate a directory from which Node can resolve ``jsdom``.

    jsdom is an optional developer dependency: it is not vendored in this repo
    and there is no package.json at the root. Candidate roots are probed in
    order and the first one from which ``require.resolve('jsdom')`` succeeds is
    used. Returns None when jsdom is not installed anywhere we can see, in
    which case these tests skip rather than fail -- a missing optional test
    dependency is not a product defect.
    """
    if NODE is None:
        return None

    candidates = []
    env_dir = os.environ.get("FILEBROWSER_JSDOM_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path(__file__).parent.parent)  # repo root
    candidates.append(Path.cwd())

    for candidate in candidates:
        if not candidate.is_dir():
            continue
        probe = subprocess.run(
            [NODE, "-e", "require.resolve('jsdom')"],
            capture_output=True,
            text=True,
            cwd=str(candidate),
        )
        if probe.returncode == 0:
            return candidate
    return None


JSDOM_CWD = _find_jsdom_cwd()

requires_node = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the JS rewrite-image-src module"
)

requires_jsdom = pytest.mark.skipif(
    JSDOM_CWD is None,
    reason=(
        "jsdom is not resolvable by node; install it (npm install jsdom) or set "
        "FILEBROWSER_JSDOM_DIR to a directory whose node_modules contains it"
    ),
)


def _run_dom_rewrite_scenario(current_file: str, html_fragment: str) -> str:
    """
    Simulate the DOM-mutation step from renderMarkdown:
      1. Create a <template> element (via jsdom).
      2. Set template.innerHTML = html_fragment.
      3. For each <img>, call rewriteImageSrc(currentFile, img.getAttribute('src')).
      4. Return template.innerHTML.

    Uses Node's built-in `require` for jsdom (CJS) and a dynamic import() for
    the ESM rewrite-image-src.js module.
    """
    assert NODE is not None
    module_url = REWRITER_JS.resolve().as_uri()

    # This script uses a top-level async IIFE so it can await the ESM import.
    # We run it as a CJS script (--input-type=commonjs) so that `require` is
    # available for jsdom, while still being able to import() the ESM module.
    script = f"""
(async () => {{
    const {{ JSDOM }} = require('jsdom');
    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>');
    const {{ document }} = dom.window;

    // Import the ESM rewriter
    const {{ rewriteImageSrc }} = await import({json.dumps(module_url)});

    const currentFile = {json.dumps(current_file)};
    const htmlFragment = {json.dumps(html_fragment)};

    const template = document.createElement('template');
    template.innerHTML = htmlFragment;
    template.content.querySelectorAll('img').forEach((img) => {{
        img.src = rewriteImageSrc(currentFile, img.getAttribute('src') || '');
    }});

    process.stdout.write(template.innerHTML);
}})();
"""
    result = subprocess.run(
        [NODE, "--input-type=commonjs", "-e", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(JSDOM_CWD),  # a dir from which node can resolve jsdom
    )
    return result.stdout


@requires_node
@requires_jsdom
class TestDomLevelImageRewrite:
    """DOM-level proof that renderMarkdown rewrites relative and leaves absolute sources."""

    def test_relative_src_is_rewritten(self):
        """A relative img src is rewritten to /api/files/content?path=..."""
        result = _run_dom_rewrite_scenario(
            "docs/page.md",
            '<p>Hello <img src="img/diagram.png"></p>',
        )
        assert '/api/files/content?path=docs%2Fimg%2Fdiagram.png' in result, (
            f"Expected rewritten API URL in output, got: {result!r}"
        )
        # The original relative path must not appear as a bare src
        assert 'src="img/diagram.png"' not in result

    def test_https_src_is_unchanged(self):
        """An https:// img src passes through byte-for-byte."""
        url = "https://example.com/logo.png"
        result = _run_dom_rewrite_scenario(
            "docs/page.md",
            f'<p><img src="{url}"></p>',
        )
        assert url in result, (
            f"Expected absolute URL to be unchanged, got: {result!r}"
        )
        assert '/api/files/content' not in result

    def test_http_src_is_unchanged(self):
        """An http:// img src passes through byte-for-byte."""
        url = "http://example.com/image.jpg"
        result = _run_dom_rewrite_scenario(
            "readme.md",
            f'<img src="{url}">',
        )
        assert url in result

    def test_protocol_relative_src_is_unchanged(self):
        """A protocol-relative //... img src passes through unchanged."""
        url = "//cdn.example.com/img.svg"
        result = _run_dom_rewrite_scenario(
            "readme.md",
            f'<img src="{url}">',
        )
        assert url in result
        assert '/api/files/content' not in result

    def test_data_uri_is_unchanged(self):
        """A data: URI passes through unchanged."""
        uri = "data:image/png;base64,iVBORw0KGgo="
        result = _run_dom_rewrite_scenario(
            "docs/page.md",
            f'<img src="{uri}">',
        )
        assert uri in result
        assert '/api/files/content' not in result

    def test_mixed_fragment_rewrites_only_relative(self):
        """In a fragment with both relative and absolute imgs, only relative is rewritten."""
        result = _run_dom_rewrite_scenario(
            "notes/readme.md",
            '<img src="./fig.svg"><img src="https://example.com/ext.png">',
        )
        assert '/api/files/content?path=notes%2Ffig.svg' in result
        assert 'https://example.com/ext.png' in result
        # The relative src must be gone
        assert 'src="./fig.svg"' not in result

    def test_parent_segment_resolved_in_dom(self):
        """A ../relative src is fully resolved (no .. in the output path)."""
        result = _run_dom_rewrite_scenario(
            "docs/sub/page.md",
            '<img src="../assets/logo.png">',
        )
        assert '/api/files/content?path=docs%2Fassets%2Flogo.png' in result
        assert '..' not in result
