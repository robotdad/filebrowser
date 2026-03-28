# Terminal Here — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add an interactive terminal panel to the filebrowser web app, allowing users to open a shell at any browsed directory.

**Architecture:** Frontend wraps xterm.js (loaded via esm.sh CDN, matching the existing no-build-step pattern) in a Preact component. Backend exposes a FastAPI WebSocket endpoint at `/api/terminal` that authenticates via session cookie or `X-Authenticated-User` header, spawns a PTY using Python's stdlib `pty` module, and bridges I/O bidirectionally using asyncio. The terminal panel renders in a third grid column (side, default) or as a bottom row, with user-swappable dock position persisted in localStorage.

**Tech Stack:** Python stdlib (`pty`, `asyncio`, `fcntl`, `termios`, `struct`, `os`, `signal`, `json`), FastAPI WebSocket, xterm.js v6 + @xterm/addon-fit via esm.sh CDN, Preact/HTM

---

## Codebase Orientation

All paths are relative to the repository root: `/home/robotdad/repos/files/filebrowser/`

| What | Where |
|------|-------|
| Python package | `filebrowser/` |
| Routes | `filebrowser/routes/` (auth.py, files.py) |
| Config | `filebrowser/config.py` — `Settings` dataclass, `settings` singleton |
| Auth utilities | `filebrowser/auth.py` — `validate_session_token()`, `require_auth()` |
| App entrypoint | `filebrowser/main.py` — creates FastAPI app, includes routers, mounts static |
| Static files | `filebrowser/static/` — index.html, js/, css/ |
| Frontend components | `filebrowser/static/js/components/` — layout.js, actions.js, context-menu.js, etc. |
| Tests | `tests/` — pytest, uses `FastAPI()` + `TestClient`, `dependency_overrides` for auth bypass |
| README | `README.md` |

**Key conventions:**
- Routes use `APIRouter(prefix="/api/...", tags=[...])` and `Depends(require_auth)` for auth
- Tests create a fresh `FastAPI()` app per fixture, do NOT import `main.app`
- Frontend uses `import { html } from '../html.js'` (HTM bound to Preact's `h`) — no JSX, no build step
- CSS uses custom properties in `:root`, dark mode via `@media (prefers-color-scheme: dark)`
- Icons from Phosphor Icons: `<i class="ph ph-icon-name"></i>`

---

## Task 1: Add `terminal_enabled` Config Setting

**Files:**
- Modify: `filebrowser/config.py` (line 22, before the closing of the class)
- Modify: `tests/test_config.py` (add test at end of file)

**Step 1: Write the failing test**

Add to the end of `tests/test_config.py`:

```python
def test_settings_terminal_enabled_defaults_true():
    from filebrowser.config import Settings

    s = Settings()
    assert s.terminal_enabled is True


def test_settings_terminal_enabled_reads_env(monkeypatch):
    from filebrowser.config import Settings

    monkeypatch.setenv("FILEBROWSER_TERMINAL_ENABLED", "false")
    s = Settings()
    assert s.terminal_enabled is False
```

**Step 2: Run test to verify it fails**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/test_config.py::test_settings_terminal_enabled_defaults_true -v
```

Expected: FAIL — `Settings` has no attribute `terminal_enabled`

**Step 3: Write the implementation**

In `filebrowser/config.py`, add a new field to the `Settings` dataclass, after the `secure_cookies` field (line 21):

```python
    terminal_enabled: bool = field(
        default_factory=lambda: (
            os.environ.get("FILEBROWSER_TERMINAL_ENABLED", "true").lower() == "true"
        )
    )
```

The full `config.py` should now read:

```python
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    home_dir: Path = field(default_factory=Path.home)
    session_timeout: int = 2592000  # 30 days in seconds
    upload_max_size: int = 1_073_741_824  # 1 GB in bytes
    secret_key: str = field(
        default_factory=lambda: os.environ.get(
            "FILEBROWSER_SECRET_KEY", secrets.token_hex(32)
        )
    )
    secure_cookies: bool = field(
        default_factory=lambda: (
            os.environ.get("FILEBROWSER_SECURE_COOKIES", "false").lower() == "true"
        )
    )
    terminal_enabled: bool = field(
        default_factory=lambda: (
            os.environ.get("FILEBROWSER_TERMINAL_ENABLED", "true").lower() == "true"
        )
    )


settings = Settings()
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/test_config.py -v
```

Expected: ALL PASS (existing + 2 new)

**Step 5: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/config.py tests/test_config.py && git commit -m "feat(config): add terminal_enabled setting with env var support"
```

---

## Task 2: Wire Terminal Router into main.py

**Files:**
- Create: `filebrowser/routes/terminal.py` (stub router only)
- Modify: `filebrowser/main.py` (conditional import + include_router)

**Step 1: Create the stub router**

Create `filebrowser/routes/terminal.py`:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/terminal", tags=["terminal"])
```

**Step 2: Update main.py to conditionally include the terminal router**

The full `filebrowser/main.py` should now read:

```python
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from filebrowser.routes import auth, files
from filebrowser.config import settings

app = FastAPI(title="File Browser", docs_url=None, redoc_url=None)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
    )


app.include_router(auth.router)
app.include_router(files.router)

if settings.terminal_enabled:
    from filebrowser.routes import terminal

    app.include_router(terminal.router)

static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

Key detail: the terminal router MUST be included BEFORE the static mount (the static mount is a catch-all). The conditional import is inside the `if` block so the module isn't loaded when terminals are disabled.

**Step 3: Verify existing tests still pass**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/ -v
```

Expected: ALL PASS (no regressions)

**Step 4: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/routes/terminal.py filebrowser/main.py && git commit -m "feat(terminal): add stub terminal router with conditional registration"
```

---

## Task 3: Terminal WebSocket — Authentication

**Files:**
- Modify: `filebrowser/routes/terminal.py` (add WebSocket endpoint with auth)
- Create: `tests/test_terminal.py` (auth rejection tests)

**Step 1: Write the failing tests**

Create `tests/test_terminal.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from filebrowser.routes.terminal import router as terminal_router


@pytest.fixture
def terminal_client():
    """Client with terminal router but NO auth bypass — tests rejection."""
    app = FastAPI()
    app.include_router(terminal_router)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed_terminal_client():
    """Client with terminal router and auth via X-Authenticated-User header."""
    app = FastAPI()
    app.include_router(terminal_router)
    with TestClient(app) as c:
        yield c


class TestTerminalAuth:
    def test_rejects_unauthenticated_websocket(self, terminal_client):
        """WebSocket without session cookie or auth header should be rejected."""
        with pytest.raises(Exception):
            with terminal_client.websocket_connect("/api/terminal") as ws:
                ws.receive_text()

    def test_accepts_authenticated_websocket(self, authed_terminal_client):
        """WebSocket with X-Authenticated-User header should connect."""
        with authed_terminal_client.websocket_connect(
            "/api/terminal",
            headers={"X-Authenticated-User": "testuser"},
        ) as ws:
            # Connection accepted — just close cleanly
            ws.close()
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/test_terminal.py -v
```

Expected: FAIL — the WebSocket endpoint doesn't exist yet (only the stub router)

**Step 3: Implement the WebSocket endpoint with auth**

Replace the contents of `filebrowser/routes/terminal.py` with:

```python
import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import termios
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from filebrowser.auth import validate_session_token
from filebrowser.config import settings

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


def _authenticate_websocket(websocket: WebSocket) -> str | None:
    """Authenticate a WebSocket using the same logic as require_auth.

    Checks X-Authenticated-User header first (frontdoor/proxy mode),
    then falls back to session cookie validation.
    Returns the username or None if unauthenticated.
    """
    remote_user = websocket.headers.get("X-Authenticated-User")
    if remote_user:
        return remote_user

    token = websocket.cookies.get("session")
    if not token:
        return None
    return validate_session_token(token, settings.secret_key, settings.session_timeout)


def _resolve_cwd(path: str) -> Path | None:
    """Resolve a relative path to an absolute directory within home_dir.

    Returns the resolved Path if valid, None if outside home_dir or not a directory.
    """
    if path:
        target = (settings.home_dir / path).resolve()
    else:
        target = settings.home_dir.resolve()

    # Ensure the path is within the allowed root
    try:
        target.relative_to(settings.home_dir.resolve())
    except ValueError:
        return None

    # Must be a directory (or home_dir itself)
    if not target.is_dir():
        return None

    return target


async def _pty_to_ws(master_fd: int, websocket: WebSocket) -> None:
    """Read PTY output in a thread and forward to WebSocket."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            data = await loop.run_in_executor(None, os.read, master_fd, 4096)
        except OSError:
            break
        if not data:
            break
        await websocket.send_text(data.decode(errors="replace"))


async def _ws_to_pty(master_fd: int, websocket: WebSocket) -> None:
    """Read WebSocket messages and write to PTY (or handle resize)."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            break

        text = message.get("text", "")
        if not text:
            continue

        # Check for resize control message
        if text.startswith("{"):
            try:
                payload = json.loads(text)
                if payload.get("type") == "resize":
                    cols = payload.get("cols", 80)
                    rows = payload.get("rows", 24)
                    winsize = struct.pack("HHHH", rows, cols, 0, 0)
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                    continue
            except (json.JSONDecodeError, KeyError, OSError):
                pass

        os.write(master_fd, text.encode())


@router.websocket("")
async def terminal_ws(websocket: WebSocket, path: str = ""):
    """WebSocket endpoint for interactive terminal sessions.

    Query params:
        path: Directory path (relative to home_dir) to use as CWD.
              Defaults to home_dir if empty.
    """
    # --- Auth ---
    username = _authenticate_websocket(websocket)
    if not username:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # --- Resolve CWD ---
    cwd = _resolve_cwd(path)
    if cwd is None:
        await websocket.close(code=4003, reason="Invalid path")
        return

    await websocket.accept()

    # --- Spawn PTY ---
    master_fd, slave_fd = pty.openpty()

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["HOME"] = str(settings.home_dir)
    env["USER"] = username

    shell = os.environ.get("SHELL", "/bin/bash")

    pid = os.fork()
    if pid == 0:
        # Child process — become the shell
        os.close(master_fd)
        os.setsid()
        # Set the slave as the controlling terminal
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)
        os.chdir(str(cwd))
        os.execvpe(shell, [shell], env)

    # Parent process
    os.close(slave_fd)

    try:
        pty_task = asyncio.create_task(_pty_to_ws(master_fd, websocket))
        ws_task = asyncio.create_task(_ws_to_pty(master_fd, websocket))

        done, pending = await asyncio.wait(
            [pty_task, ws_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        # Clean up PTY and child process
        try:
            os.kill(pid, signal.SIGHUP)
            os.waitpid(pid, os.WNOHANG)
        except (OSError, ChildProcessError):
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/test_terminal.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/routes/terminal.py tests/test_terminal.py && git commit -m "feat(terminal): WebSocket endpoint with auth, PTY spawn, bidirectional bridge"
```

---

## Task 4: Terminal Backend Tests — PTY Lifecycle

**Files:**
- Modify: `tests/test_terminal.py` (add PTY lifecycle + path validation tests)

**Step 1: Add PTY lifecycle and path validation tests**

Append these test classes to `tests/test_terminal.py`:

```python
class TestTerminalPTY:
    def test_terminal_echoes_input(self, authed_terminal_client, tmp_path):
        """Send a command and verify we get output back from the shell."""
        import time

        with authed_terminal_client.websocket_connect(
            "/api/terminal",
            headers={"X-Authenticated-User": "testuser"},
        ) as ws:
            # Give the shell a moment to start
            time.sleep(0.3)
            # Drain any initial prompt output
            try:
                while True:
                    ws.receive_text(mode="text")
            except Exception:
                pass

            # Send a command that produces known output
            ws.send_text("echo HELLO_TERMINAL\n")
            time.sleep(0.5)

            # Collect output — look for our marker string
            output = ""
            try:
                for _ in range(20):
                    output += ws.receive_text(mode="text")
            except Exception:
                pass

            assert "HELLO_TERMINAL" in output

    def test_terminal_resize_message(self, authed_terminal_client):
        """Resize control message should not crash the connection."""
        import json
        import time

        with authed_terminal_client.websocket_connect(
            "/api/terminal",
            headers={"X-Authenticated-User": "testuser"},
        ) as ws:
            time.sleep(0.3)
            resize_msg = json.dumps({"type": "resize", "cols": 120, "rows": 40})
            ws.send_text(resize_msg)
            # If we get here without exception, resize was handled
            time.sleep(0.1)
            ws.close()


class TestTerminalPathValidation:
    def test_invalid_path_rejected(self, authed_terminal_client):
        """Path traversal attempt should be rejected."""
        with pytest.raises(Exception):
            with authed_terminal_client.websocket_connect(
                "/api/terminal?path=../../etc",
                headers={"X-Authenticated-User": "testuser"},
            ) as ws:
                ws.receive_text()

    def test_empty_path_uses_home_dir(self, authed_terminal_client):
        """Empty path should default to home directory and connect successfully."""
        with authed_terminal_client.websocket_connect(
            "/api/terminal?path=",
            headers={"X-Authenticated-User": "testuser"},
        ) as ws:
            ws.close()
```

**Step 2: Run all terminal tests**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/test_terminal.py -v
```

Expected: ALL PASS

Note: The echo test may need the `time.sleep` values adjusted depending on system speed. If the test is flaky, increase the sleep to `0.5` and `1.0` respectively.

**Step 3: Run the full test suite to confirm no regressions**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/ -v
```

Expected: ALL PASS

**Step 4: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add tests/test_terminal.py && git commit -m "test(terminal): add PTY lifecycle, resize, and path validation tests"
```

---

## Task 5: Frontend — xterm.js CDN Imports

**Files:**
- Modify: `filebrowser/static/index.html`

**Step 1: Add xterm.js CSS link**

In `filebrowser/static/index.html`, add a new `<link>` tag after the highlight.js dark CSS link (after line 17, before the `<script type="importmap">`):

```html
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xterm/xterm@6/css/xterm.min.css">
```

**Step 2: Add import map entries**

In the `"imports"` block of the `<script type="importmap">` (after the `"marked"` entry), add:

```json
            "@xterm/xterm": "https://esm.sh/@xterm/xterm@6.0.0",
            "@xterm/addon-fit": "https://esm.sh/@xterm/addon-fit@0.11.0"
```

The full `<script type="importmap">` block should now read:

```html
    <script type="importmap">
    {
        "imports": {
            "preact": "https://esm.sh/preact@10",
            "preact/hooks": "https://esm.sh/preact@10/hooks",
            "htm": "https://esm.sh/htm@3",
            "highlight.js": "https://esm.sh/highlight.js@11",
            "marked": "https://esm.sh/marked@15",
            "@xterm/xterm": "https://esm.sh/@xterm/xterm@6.0.0",
            "@xterm/addon-fit": "https://esm.sh/@xterm/addon-fit@0.11.0"
        }
    }
    </script>
```

**Step 3: Verify the HTML is valid**

Open the file and confirm the JSON in the import map is valid (no trailing commas after the last entry, proper quoting). The `marked` line now needs a trailing comma since it's no longer the last entry.

**Step 4: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/index.html && git commit -m "feat(terminal): add xterm.js CDN imports to index.html"
```

---

## Task 6: Frontend — Terminal Preact Component

**Files:**
- Create: `filebrowser/static/js/components/terminal.js`

**Step 1: Create the Terminal component**

Create `filebrowser/static/js/components/terminal.js`:

```javascript
import { useEffect, useRef, useCallback } from 'preact/hooks';
import { html } from '../html.js';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';

/**
 * TerminalPanel — wraps xterm.js in a Preact component connected via WebSocket.
 *
 * Props:
 *   cwd          — directory path (relative to home_dir) for the shell's CWD
 *   onClose()    — callback to close the terminal panel
 *   dockPosition — 'side' | 'bottom'
 *   onToggleDock — callback to swap dock position
 */
export function TerminalPanel({ cwd, onClose, dockPosition, onToggleDock }) {
    const containerRef = useRef(null);
    const termRef = useRef(null);
    const wsRef = useRef(null);
    const fitRef = useRef(null);

    useEffect(() => {
        if (!containerRef.current) return;

        // --- Create terminal instance ---
        const term = new Terminal({
            cursorBlink: true,
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Consolas', monospace",
            theme: {
                background: '#1c1c1e',
                foreground: '#f5f5f7',
                cursor: '#f5f5f7',
                selectionBackground: 'rgba(255, 255, 255, 0.2)',
                black: '#1c1c1e',
                red: '#ff3b30',
                green: '#34c759',
                yellow: '#ff9500',
                blue: '#007aff',
                magenta: '#af52de',
                cyan: '#5ac8fa',
                white: '#f5f5f7',
                brightBlack: '#636366',
                brightRed: '#ff6961',
                brightGreen: '#4cd964',
                brightYellow: '#ffcc00',
                brightBlue: '#5ac8fa',
                brightMagenta: '#da8fff',
                brightCyan: '#70d7ff',
                brightWhite: '#ffffff',
            },
        });

        const fitAddon = new FitAddon();
        term.loadAddon(fitAddon);
        term.open(containerRef.current);

        termRef.current = term;
        fitRef.current = fitAddon;

        // Initial fit after a frame to ensure container has dimensions
        requestAnimationFrame(() => {
            try { fitAddon.fit(); } catch {}
        });

        // --- Connect WebSocket ---
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}/api/terminal?path=${encodeURIComponent(cwd || '')}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            // Send initial size
            const dims = fitAddon.proposeDimensions();
            if (dims) {
                ws.send(JSON.stringify({ type: 'resize', cols: dims.cols, rows: dims.rows }));
            }
        };

        ws.onmessage = (event) => {
            term.write(event.data);
        };

        ws.onclose = () => {
            term.write('\r\n\x1b[90m[Terminal session ended]\x1b[0m\r\n');
        };

        ws.onerror = () => {
            term.write('\r\n\x1b[31m[Connection error]\x1b[0m\r\n');
        };

        // --- Terminal input → WebSocket ---
        const dataDisposable = term.onData((data) => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(data);
            }
        });

        // --- Resize handling ---
        const resizeDisposable = term.onResize(({ cols, rows }) => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'resize', cols, rows }));
            }
        });

        // Fit on window resize
        const handleWindowResize = () => {
            try { fitAddon.fit(); } catch {}
        };
        window.addEventListener('resize', handleWindowResize);

        // ResizeObserver for container size changes (e.g., panel drag resize)
        const resizeObserver = new ResizeObserver(() => {
            try { fitAddon.fit(); } catch {}
        });
        resizeObserver.observe(containerRef.current);

        // --- Cleanup ---
        return () => {
            resizeObserver.disconnect();
            window.removeEventListener('resize', handleWindowResize);
            dataDisposable.dispose();
            resizeDisposable.dispose();
            if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                ws.close();
            }
            term.dispose();
            termRef.current = null;
            wsRef.current = null;
            fitRef.current = null;
        };
    }, [cwd]);

    // Re-fit when dock position changes
    useEffect(() => {
        if (fitRef.current) {
            requestAnimationFrame(() => {
                try { fitRef.current.fit(); } catch {}
            });
        }
    }, [dockPosition]);

    return html`
        <div class="terminal-panel">
            <div class="terminal-panel-header">
                <span class="terminal-panel-title">
                    <i class="ph ph-terminal-window"></i>
                    Terminal
                </span>
                <div class="terminal-panel-actions">
                    <button
                        class="terminal-dock-btn"
                        onClick=${onToggleDock}
                        title=${dockPosition === 'side' ? 'Dock to bottom' : 'Dock to side'}
                    >
                        <i class="ph ${dockPosition === 'side' ? 'ph-rows' : 'ph-columns'}"></i>
                    </button>
                    <button
                        class="terminal-close-btn"
                        onClick=${onClose}
                        title="Close terminal"
                    >
                        <i class="ph ph-x"></i>
                    </button>
                </div>
            </div>
            <div class="terminal-container" ref=${containerRef}></div>
        </div>
    `;
}
```

**Step 2: Verify the file was created**

```bash
cat filebrowser/static/js/components/terminal.js | head -5
```

Expected: the first 5 lines of the file above

**Step 3: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/components/terminal.js && git commit -m "feat(terminal): add TerminalPanel Preact component with xterm.js"
```

---

## Task 7: CSS — Terminal Panel Styles

**Files:**
- Modify: `filebrowser/static/css/styles.css` (append at end)

**Step 1: Add terminal panel CSS**

Append the following to the end of `filebrowser/static/css/styles.css`:

```css

/* ============================================================
   TERMINAL PANEL
   ============================================================ */

/* --- Layout: Side dock (default) --- */
.main-content.terminal-side {
    grid-template-columns: var(--sidebar-width) 1fr var(--terminal-width, 400px);
}

/* --- Layout: Bottom dock --- */
.main-content.terminal-bottom {
    grid-template-columns: var(--sidebar-width) 1fr;
    grid-template-rows: 1fr var(--terminal-height, 300px);
}
.main-content.terminal-bottom .sidebar {
    grid-row: 1 / -1;
}
.main-content.terminal-bottom .terminal-panel {
    grid-column: 2;
    grid-row: 2;
}

/* --- Terminal panel container --- */
.terminal-panel {
    display: flex;
    flex-direction: column;
    background: #1c1c1e;
    border-left: 0.5px solid var(--border-color);
    overflow: hidden;
    min-width: 0;
    min-height: 0;
}
.main-content.terminal-bottom .terminal-panel {
    border-left: none;
    border-top: 0.5px solid var(--border-color);
}

/* --- Terminal panel header bar --- */
.terminal-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 12px;
    background: #2c2c2e;
    border-bottom: 0.5px solid rgba(84, 84, 88, 0.36);
    flex-shrink: 0;
    min-height: 36px;
}
.terminal-panel-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    color: #98989d;
    user-select: none;
}
.terminal-panel-title i {
    font-size: 14px;
}
.terminal-panel-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}
.terminal-dock-btn,
.terminal-close-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border-radius: 6px;
    background: transparent;
    border: none;
    cursor: pointer;
    color: #98989d;
    font-size: 14px;
    transition: background 120ms ease, color 120ms ease;
}
.terminal-dock-btn:hover,
.terminal-close-btn:hover {
    background: rgba(120, 120, 128, 0.36);
    color: #f5f5f7;
}
.terminal-close-btn:hover {
    color: #ff3b30;
}

/* --- Terminal content area (xterm.js container) --- */
.terminal-container {
    flex: 1;
    min-height: 0;
    padding: 4px;
    overflow: hidden;
}
.terminal-container .xterm {
    height: 100%;
}
.terminal-container .xterm-viewport {
    overflow-y: auto !important;
}

/* --- Resize handle: side dock (horizontal) --- */
.terminal-resize-handle-h {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 8px;
    transform: translateX(-50%);
    cursor: col-resize;
    z-index: 10;
}
.terminal-resize-handle-h::after {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    left: 50%;
    width: 2px;
    transform: translateX(-50%);
    background: transparent;
    transition: background 0.15s;
}
.terminal-resize-handle-h:hover::after {
    background: var(--accent);
}

/* --- Resize handle: bottom dock (vertical) --- */
.terminal-resize-handle-v {
    position: absolute;
    left: 0;
    right: 0;
    height: 8px;
    transform: translateY(-50%);
    cursor: row-resize;
    z-index: 10;
}
.terminal-resize-handle-v::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    height: 2px;
    transform: translateY(-50%);
    background: transparent;
    transition: background 0.15s;
}
.terminal-resize-handle-v:hover::after {
    background: var(--accent);
}

/* --- Mobile: hide terminal panel --- */
@media (max-width: 768px) {
    .main-content.terminal-side {
        grid-template-columns: 1fr;
    }
    .terminal-panel {
        display: none;
    }
}
```

**Step 2: Verify no syntax issues**

```bash
tail -20 filebrowser/static/css/styles.css
```

Expected: last CSS rules from the terminal section

**Step 3: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/css/styles.css && git commit -m "feat(terminal): add CSS for terminal panel, both dock positions, and resize handles"
```

---

## Task 8: Layout Integration — Terminal State + Side Panel

**Files:**
- Modify: `filebrowser/static/js/components/layout.js`

This is the largest frontend task. We're adding terminal state management, the `<TerminalPanel>` component rendering, and the resize handle — all wired into the existing layout grid.

**Step 1: Add the TerminalPanel import**

At the top of `filebrowser/static/js/components/layout.js`, after the existing imports (after line 9), add:

```javascript
import { TerminalPanel } from './terminal.js';
```

**Step 2: Add terminal state variables**

Inside the `Layout` function, after the `Feature state` comment block (after line 30, the `dragCounter` ref), add:

```javascript
    // ── Terminal state ──────────────────────────────────────────
    const [terminalOpen, setTerminalOpen] = useState(false);
    const [terminalCwd, setTerminalCwd] = useState('');
    const [terminalDock, setTerminalDock] = useState(() => {
        try { return localStorage.getItem('fb-terminal-dock') || 'side'; }
        catch { return 'side'; }
    });
    const [terminalSize, setTerminalSize] = useState(() => {
        try { return parseInt(localStorage.getItem('fb-terminal-size'), 10) || 400; }
        catch { return 400; }
    });
    const isTerminalResizing = useRef(false);
```

**Step 3: Add terminal helper functions**

After the terminal state variables, add:

```javascript
    const openTerminal = (path) => {
        setTerminalCwd(path ?? currentPath);
        setTerminalOpen(true);
    };

    const closeTerminal = () => {
        setTerminalOpen(false);
    };

    const toggleTerminalDock = () => {
        setTerminalDock((prev) => {
            const next = prev === 'side' ? 'bottom' : 'side';
            localStorage.setItem('fb-terminal-dock', next);
            return next;
        });
    };
```

**Step 4: Add terminal resize handle logic**

After the `toggleTerminalDock` function, add:

```javascript
    const startTerminalResize = (e) => {
        e.preventDefault();
        isTerminalResizing.current = true;
        const isSide = terminalDock === 'side';
        document.body.style.cursor = isSide ? 'col-resize' : 'row-resize';
        document.body.style.userSelect = 'none';

        const onMove = (ev) => {
            if (!isTerminalResizing.current) return;
            if (isSide) {
                const newWidth = window.innerWidth - ev.clientX;
                setTerminalSize(Math.min(Math.max(newWidth, 200), 800));
            } else {
                const mainContent = document.querySelector('.main-content');
                const rect = mainContent?.getBoundingClientRect();
                if (rect) {
                    const newHeight = rect.bottom - ev.clientY;
                    setTerminalSize(Math.min(Math.max(newHeight, 150), 600));
                }
            }
        };
        const onUp = () => {
            isTerminalResizing.current = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            localStorage.setItem('fb-terminal-size', String(terminalSize));
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    };
```

**Step 5: Add Ctrl+\` keyboard shortcut**

In the existing keyboard shortcuts `useEffect` (the handler function starting around line 62), add a new shortcut inside the handler, after the Escape handler:

```javascript
            // Ctrl+` → toggle terminal
            if ((e.metaKey || e.ctrlKey) && e.key === '`') {
                e.preventDefault();
                setTerminalOpen((prev) => {
                    if (!prev) setTerminalCwd(currentPath);
                    return !prev;
                });
            }
```

**Step 6: Update the main-content div to include terminal CSS class and size variable**

Find the `main-content` div (around line 248):

```javascript
            <div class="main-content" style=${{ '--sidebar-width': `${sidebarWidth}px` }}>
```

Replace it with:

```javascript
            <div class="main-content ${terminalOpen ? `terminal-${terminalDock}` : ''}" style=${{
                '--sidebar-width': `${sidebarWidth}px`,
                ...(terminalOpen && terminalDock === 'side' ? { '--terminal-width': `${terminalSize}px` } : {}),
                ...(terminalOpen && terminalDock === 'bottom' ? { '--terminal-height': `${terminalSize}px` } : {}),
            }}>
```

**Step 7: Add the TerminalPanel and resize handle to the layout**

After the closing `</main>` tag (around line 321), and before the closing `</div>` of `main-content` (around line 322), add:

```javascript
                ${terminalOpen && html`
                    <div
                        class="${terminalDock === 'side' ? 'terminal-resize-handle-h' : 'terminal-resize-handle-v'}"
                        style=${{
                            ...(terminalDock === 'side' ? { right: `${terminalSize}px` } : {}),
                        }}
                        onMouseDown=${startTerminalResize}
                    ></div>
                    <${TerminalPanel}
                        cwd=${terminalCwd}
                        onClose=${closeTerminal}
                        dockPosition=${terminalDock}
                        onToggleDock=${toggleTerminalDock}
                    />
                `}
```

**Step 8: Pass `openTerminal` to ContextMenu and ActionBar**

Update the `<ContextMenu>` component (around line 345) to pass the terminal handler:

```javascript
            <${ContextMenu}
                menu=${contextMenu}
                onClose=${() => setContextMenu(null)}
                onOpen=${handleCtxOpen}
                onDownload=${handleCtxDownload}
                onRename=${handleCtxRename}
                onDelete=${handleCtxDelete}
                onCopyPath=${handleCtxCopyPath}
                onTogglePin=${toggleFavorite}
                isPinned=${contextMenu && favorites.includes(contextMenu.path)}
                onOpenTerminal=${openTerminal}
            />
```

Update the `<ActionBar>` component (around line 325) to pass terminal props:

```javascript
            <${ActionBar}
                currentPath=${currentPath}
                selectedFile=${selectedFile}
                selectedFiles=${selectedFiles}
                onRefresh=${refresh}
                onClearSelection=${clearSelection}
                showUpload=${showUpload}
                onShowUpload=${() => setShowUpload(true)}
                onHideUpload=${() => setShowUpload(false)}
                terminalOpen=${terminalOpen}
                onToggleTerminal=${() => terminalOpen ? closeTerminal() : openTerminal()}
            />
```

**Step 9: Verify no JavaScript syntax errors by loading the page**

Start the dev server (if not running) and load the page in a browser. Check the browser console for import/syntax errors.

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/ -v
```

Expected: ALL PASS (backend tests still green)

**Step 10: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/components/layout.js && git commit -m "feat(terminal): integrate terminal panel into layout with state, resize, keyboard shortcut"
```

---

## Task 9: Context Menu — "Open Terminal Here"

**Files:**
- Modify: `filebrowser/static/js/components/context-menu.js`

**Step 1: Add `onOpenTerminal` prop to the component**

Update the function signature on line 18 to include `onOpenTerminal`:

```javascript
export function ContextMenu({ menu, onClose, onOpen, onDownload, onRename, onDelete, onCopyPath, onTogglePin, isPinned, onOpenTerminal }) {
```

**Step 2: Add "Open Terminal Here" menu item for directories**

Inside the template, after the pin/unpin block for directories (after the closing `\`}` on line 78), add:

```javascript
            ${menu.type === 'directory' && onOpenTerminal && html`
                <button class="context-menu-item" onClick=${act(onOpenTerminal)}>
                    <i class="ph ph-terminal-window"></i> Open Terminal Here
                </button>
                <div class="context-menu-divider"></div>
            `}
```

**Step 3: Update the estimated menu height**

On line 46, the `menuH` calculation determines viewport clamping. Update the directory height to account for the new item:

```javascript
    const menuH = menu.type === 'file' ? 200 : 220;
```

**Step 4: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/components/context-menu.js && git commit -m "feat(terminal): add 'Open Terminal Here' to folder context menu"
```

---

## Task 10: Action Bar — Terminal Toggle Button

**Files:**
- Modify: `filebrowser/static/js/components/actions.js`

**Step 1: Add terminal props to the function signature**

Update the `ActionBar` function destructuring (line 6) to include the new props:

```javascript
export function ActionBar({
    currentPath,
    selectedFile,
    selectedFiles,
    onRefresh,
    onClearSelection,
    showUpload,
    onShowUpload,
    onHideUpload,
    terminalOpen,
    onToggleTerminal,
}) {
```

**Step 2: Add terminal button to the normal toolbar**

In the normal toolbar section (around line 110), add a terminal toggle button after the opening `<div class="action-bar">` and before the Upload button:

```javascript
            <button onClick=${onToggleTerminal} title="Toggle terminal (Ctrl+\`)">
                <i class="ph ${terminalOpen ? 'ph-terminal-window-fill' : 'ph-terminal-window'}"></i> Terminal
            </button>
```

The return for the normal toolbar should now read:

```javascript
    return html`
        <div class="action-bar">
            <button onClick=${onToggleTerminal} title="Toggle terminal (Ctrl+\`)">
                <i class="ph ${terminalOpen ? 'ph-terminal-window-fill' : 'ph-terminal-window'}"></i> Terminal
            </button>
            <button onClick=${() => onShowUpload()}>
                <i class="ph ph-upload-simple"></i> Upload
            </button>
            ...rest of existing buttons...
        </div>
    `;
```

**Step 3: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/components/actions.js && git commit -m "feat(terminal): add terminal toggle button to action bar"
```

---

## Task 11: README — Document the Terminal Feature

**Files:**
- Modify: `README.md`

**Step 1: Update the "What it does" section**

In `README.md`, add a new bullet to the "What it does" list (after the "Context menus" bullet on line 11):

```markdown
- **Terminal** -- open an interactive shell in any directory, docked to the side (default) or bottom of the preview pane, with drag-to-resize
```

**Step 2: Update the Layout diagram**

Replace the layout ASCII art (lines 19-38) with:

```markdown
## Layout

```
+-----------------------------------------------------------+
|  Header: breadcrumb pills | [Search Cmd+K] | user | logout|
+-----------------+--------------------------+--------------+
| [List|Grid] view|                          |              |
|                 |      Preview Pane        |   Terminal   |
|  File Tree     ||                          |  (xterm.js)  |
|  (resizable)   ||  Text: line numbers      |              |
|                ||  Code: syntax highlighted|  resizable   |
|  color-coded   ||  Markdown: fully rendered|  toggleable  |
|  file icons    ||  HTML: iframe preview    |  Ctrl+`      |
|                ||  Images: inline preview  |              |
|  right-click   ||  Audio/Video: player     |  dock: side  |
|  for context   ||  PDF: embedded viewer    |   or bottom  |
|  menu          ||                          |              |
+-----------------+--------------------------+--------------+
|  Actions: [Terminal] | upload | new folder | download ... |
|  (or batch toolbar when multi-selecting with Ctrl+click)  |
+-----------------------------------------------------------+
```
```

**Step 3: Update the Keyboard shortcuts table**

Add a new row to the keyboard shortcuts table (after the `Ctrl+K / Cmd+K` row):

```markdown
| Ctrl+` / Cmd+` | Toggle terminal panel |
```

**Step 4: Update the Configuration table**

Add a new row to the Configuration table (after the `home_dir` row):

```markdown
| `FILEBROWSER_TERMINAL_ENABLED` | `true` | Enable the interactive terminal. Set to `false` to disable. |
```

**Step 5: Update the Project structure**

Add the new files to the project structure tree. Under `routes/`:

```
      terminal.py            # /api/terminal WebSocket endpoint (PTY lifecycle)
```

Under `components/`:

```
          terminal.js       # Interactive terminal panel (xterm.js wrapper)
```

**Step 6: Update the Tech stack section**

Update the **Frontend** line to mention xterm.js:

```markdown
**Frontend** -- Preact + HTM (no build step), highlight.js (syntax), marked.js (markdown), xterm.js (terminal emulator), Phosphor Icons, Inter + JetBrains Mono fonts, all via CDN
```

Update the dependency count at the end:

```markdown
5 Python runtime dependencies. 0 frontend build tools. 0 new backend dependencies for terminal support.
```

**Step 7: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add README.md && git commit -m "docs: document terminal feature in README"
```

---

## Task 12: End-to-End Verification

**Step 1: Run the full test suite**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/ -v
```

Expected: ALL PASS (original tests + new terminal tests)

**Step 2: Start the dev server**

```bash
cd /home/robotdad/repos/files/filebrowser && uvicorn filebrowser.main:app --reload --host 0.0.0.0 --port 58080
```

**Step 3: Manual verification checklist**

1. **Page loads** — open `http://localhost:58080`, confirm no console errors
2. **Terminal button** — click "Terminal" in the action bar, verify terminal panel appears on the right side
3. **Terminal works** — type `ls` and press Enter, verify directory listing appears
4. **CWD correct** — type `pwd`, verify it shows the home directory
5. **Context menu** — right-click a folder in the sidebar, verify "Open Terminal Here" option appears
6. **Open Terminal Here** — click it, verify a terminal opens with that folder as CWD
7. **Dock swap** — click the dock toggle button (rows/columns icon) in the terminal header, verify it moves to the bottom
8. **Resize** — drag the resize handle between preview and terminal, verify it resizes
9. **Close** — click the X button in the terminal header, verify it closes
10. **Keyboard shortcut** — press Ctrl+`, verify terminal toggles open/closed
11. **Persistence** — swap to bottom dock, close terminal, reopen it, verify it remembers the bottom position

**Step 4: Run Python quality checks**

```bash
cd /home/robotdad/repos/files/filebrowser && python -m pytest tests/ -v && echo "ALL TESTS PASSED"
```

**Step 5: Final commit (if any fixups were needed)**

```bash
cd /home/robotdad/repos/files/filebrowser && git add -A && git status
```

If clean, no commit needed. If there are fixups:

```bash
git commit -m "fix: terminal integration fixups from end-to-end verification"
```

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `filebrowser/config.py` | Modify | Add `terminal_enabled` setting |
| `filebrowser/main.py` | Modify | Conditional terminal router registration |
| `filebrowser/routes/terminal.py` | **Create** | WebSocket endpoint, PTY lifecycle, auth |
| `filebrowser/static/index.html` | Modify | xterm.js CSS link + import map entries |
| `filebrowser/static/js/components/terminal.js` | **Create** | Preact xterm.js wrapper component |
| `filebrowser/static/js/components/layout.js` | Modify | Terminal state, panel rendering, resize, Ctrl+` |
| `filebrowser/static/js/components/context-menu.js` | Modify | "Open Terminal Here" on folders |
| `filebrowser/static/js/components/actions.js` | Modify | Terminal toggle button in footer |
| `filebrowser/static/css/styles.css` | Modify | Terminal panel CSS (both dock positions) |
| `tests/test_terminal.py` | **Create** | Auth, PTY lifecycle, path validation tests |
| `tests/test_config.py` | Modify | `terminal_enabled` config tests |
| `README.md` | Modify | Document the terminal feature |
