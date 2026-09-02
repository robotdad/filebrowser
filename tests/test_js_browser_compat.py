"""Guards that ensure frontend JS modules are browser-loadable.

Two checks:
  1. No file under filebrowser/static/js/ contains a `node:` import specifier
     (Node built-ins are not available in the browser).
  2. Every bare-module import specifier used by files under
     filebrowser/static/js/ resolves against the import map declared in
     filebrowser/static/index.html, either as a direct key or through a
     mapped prefix (entries ending with '/').  Relative specifiers are exempt.
"""

import json
import re
from pathlib import Path

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
JS_DIR = STATIC_DIR / "js"
INDEX_HTML = STATIC_DIR / "index.html"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_js_files():
    """Return all .js files under filebrowser/static/js/."""
    return list(JS_DIR.rglob("*.js"))


def _extract_import_map(html_path: Path) -> dict:
    """Parse the <script type="importmap"> block from index.html."""
    html = html_path.read_text()
    match = re.search(r'<script type="importmap">(.*?)</script>', html, re.DOTALL)
    assert match, "No importmap script tag found in index.html"
    return json.loads(match.group(1).strip())


def _bare_specifiers_in_file(js_path: Path) -> list[str]:
    """Return all bare-module specifiers (not relative, not node:) imported in a JS file."""
    text = js_path.read_text()
    # Match: import ... from 'specifier' or import 'specifier'
    raw = re.findall(r"""(?:import\s+.*?from\s+|import\s+)['"](.*?)['"]""", text)
    bare = []
    for spec in raw:
        if spec.startswith('.') or spec.startswith('/'):
            continue  # relative or absolute path — not a bare specifier
        bare.append(spec)
    return bare


def _specifier_resolves(specifier: str, imports: dict) -> bool:
    """Return True if specifier matches a direct key or a prefix key in the import map."""
    if specifier in imports:
        return True
    for key in imports:
        if key.endswith('/') and specifier.startswith(key):
            return True
    return False


# ---------------------------------------------------------------------------
# Test 1: No node: import specifiers in any browser-loaded JS file
# ---------------------------------------------------------------------------

class TestNoNodeSpecifiers:
    """Guard: no file under filebrowser/static/js/ may import a node: specifier."""

    def test_no_node_specifiers_in_js_files(self):
        """Fail if any .js file imports a node: specifier."""
        violations = []
        for js_file in _all_js_files():
            text = js_file.read_text()
            # Look for import ... from 'node:...' or import 'node:...'
            matches = re.findall(
                r"""(?:import\s+.*?from\s+|import\s+)['"](node:[^'"]+)['"]""",
                text,
            )
            for spec in matches:
                violations.append(f"{js_file.relative_to(STATIC_DIR)}: {spec!r}")

        assert not violations, (
            "node: import specifiers found in browser-loaded JS files "
            "(these cannot be resolved by the browser):\n"
            + "\n".join(f"  {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# Test 2: All bare-module specifiers resolve against the import map
# ---------------------------------------------------------------------------

class TestImportMapResolvability:
    """Guard: every bare-module specifier used in JS files resolves via the import map."""

    def test_all_bare_specifiers_in_import_map(self):
        """Fail if any bare specifier is not covered by the import map."""
        import_map = _extract_import_map(INDEX_HTML)
        imports = import_map.get("imports", {})

        unresolvable = []
        for js_file in _all_js_files():
            for spec in _bare_specifiers_in_file(js_file):
                if spec.startswith('node:'):
                    # node: specifiers are caught by the other test; skip here
                    continue
                if not _specifier_resolves(spec, imports):
                    unresolvable.append(
                        f"{js_file.relative_to(STATIC_DIR)}: {spec!r}"
                    )

        assert not unresolvable, (
            "Bare-module specifiers not covered by the import map in index.html:\n"
            + "\n".join(f"  {u}" for u in unresolvable)
        )
