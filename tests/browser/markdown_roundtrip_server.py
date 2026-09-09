#!/usr/bin/env python3
"""Dedicated reusable fixture server for Markdown roundtrip browser tests.

Runs filebrowser FastAPI app with:
- loopback-only binding on configurable port (default: 58388)
- isolated test HOME directory (.work/test_home)
- synthetic fixture files populated in test_home/docs
- dummy identity authentication (dummy-user) without PAM
- /test-harness route for direct component mount testing
"""
import os
import shutil
import sys
from pathlib import Path

WORKTREE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKTREE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKTREE_ROOT))

# Enforce an explicitly supplied, isolated test HOME and data dir.
WORK_DIR = WORKTREE_ROOT / ".work"


def _require_safe_work_descendant(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required for the Markdown browser fixture")
    candidate = Path(value).absolute()
    if candidate == WORK_DIR or not candidate.is_relative_to(WORK_DIR):
        raise RuntimeError(f"{name} must be a strict descendant of {WORK_DIR}")
    for part in (candidate, *candidate.parents):
        if part == WORK_DIR.parent:
            break
        if part.is_symlink():
            raise RuntimeError(f"{name} must not traverse a symlink: {part}")
    if candidate.exists() and not candidate.is_dir():
        raise RuntimeError(f"{name} must name a directory: {candidate}")
    return candidate


TEST_HOME = _require_safe_work_descendant("FILEBROWSER_FIXTURE_HOME")
TEST_DATA = _require_safe_work_descendant("FILEBROWSER_FIXTURE_DATA")
if TEST_HOME == TEST_DATA or TEST_HOME.is_relative_to(TEST_DATA) or TEST_DATA.is_relative_to(TEST_HOME):
    raise RuntimeError("fixture HOME and data directories must be separate")
TEST_DOCS = TEST_HOME / "docs"
TEST_DOCS.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(TEST_HOME)
os.environ["FILEBROWSER_DATA_DIR"] = str(TEST_DATA)
os.environ["FILEBROWSER_TERMINAL_ENABLED"] = "false"

# Seed synthetic fixtures into test_home/docs
FIXTURES_DIR = WORKTREE_ROOT / "tests" / "fixtures" / "markdown_roundtrip"
if FIXTURES_DIR.exists():
    for f in FIXTURES_DIR.glob("*"):
        if f.is_file():
            shutil.copy2(f, TEST_DOCS / f.name)

from filebrowser.config import settings
settings.home_dir = TEST_HOME
settings.data_dir = TEST_DATA
settings.terminal_enabled = False

from filebrowser.main import app
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

@app.middleware("http")
async def dummy_auth_middleware(request: Request, call_next):
    # If no session cookie and no X-Authenticated-User header, inject dummy identity
    has_session = "session" in request.cookies
    has_header = "x-authenticated-user" in request.headers
    if not has_session and not has_header:
        # Mutate ASGI scope headers
        headers = list(request.scope.get("headers", []))
        headers.append((b"x-authenticated-user", b"dummy-user"))
        request.scope["headers"] = headers
        # Also rebuild Starlette Headers
        from starlette.datastructures import Headers
        request._headers = Headers(raw=headers)
    return await call_next(request)

async def direct_mount_harness(request: Request):
    index_path = WORKTREE_ROOT / "filebrowser" / "static" / "index.html"
    index_html = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    importmap = ""
    if '<script type="importmap">' in index_html:
        start = index_html.index('<script type="importmap">')
        end = index_html.index("</script>", start) + 9
        importmap = index_html[start:end]

    return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MarkdownEditor Direct Mount Harness</title>
    {importmap}
    <link rel="stylesheet" href="/css/styles.css">
</head>
<body>
    <div id="harness-mount" style="height: 100vh; width: 100vw;"></div>
    <script type="module">
        import {{ h, render }} from 'preact';
        import {{ MarkdownEditor }} from '/js/components/markdown-editor.js';

        window.__mountEditor = function(props) {{
            const root = document.getElementById('harness-mount');
            render(h(MarkdownEditor, props), root);
        }};
    </script>
</body>
</html>
""")

# Prepend the test harness route so it takes precedence over the catch-all static mount
app.router.routes.insert(0, Route("/test-harness", direct_mount_harness, methods=["GET"]))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("FILEBROWSER_TEST_PORT", "58388"))
    print(f"Fixture home: {TEST_HOME}", flush=True)
    print(f"Fixture data: {TEST_DATA}", flush=True)
    print(f"Fixture source: {WORKTREE_ROOT}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
