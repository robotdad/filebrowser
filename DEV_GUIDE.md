# filebrowser Developer Guide

Web-based file browser, code editor, and terminal for headless Linux machines. Browse files, preview/edit code and Markdown, render DOT diagrams, and open a full terminal -- all in the browser over Tailscale.

Designed as a companion to [frontdoor](../frontdoor), sharing its auth, deployment, and infrastructure patterns.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| Web framework | FastAPI + Starlette |
| ASGI server | Uvicorn (`[standard]` extras for WebSocket support) |
| Auth | Linux PAM (`python-pam`) + HMAC-signed cookies (`itsdangerous`), frontdoor SSO integration |
| Frontend framework | Preact 10 + HTM 3 via CDN (`esm.sh`) -- zero build step |
| Code editing | CodeMirror 6 (+ `cm-lang-dot` for DOT syntax) |
| Markdown editing | Tiptap v2 WYSIWYG (+ tiptap-markdown, ProseMirror) |
| Terminal | xterm.js v6 + server-side PTY via WebSocket |
| DOT rendering | @hpcc-js/wasm + d3-graphviz (in-browser Graphviz) |
| Markdown preview | marked v15 + DOMPurify |
| Icons / Fonts | Phosphor Icons v2, Inter + JetBrains Mono (Google Fonts) |
| Reverse proxy | Caddy (`conf.d` snippet, `forward_auth` via frontdoor) |
| Networking | Tailscale (WireGuard mesh + optional certs) |
| Service manager | systemd |
| Package manager | `uv` (lockfile committed) / `pip` |
| Build backend | setuptools |
| Test framework | pytest + httpx |

No Docker, no npm, no frontend build tooling. All frontend dependencies loaded via ES module import maps in `index.html`.

## Directory Map

```
filebrowser/
|-- filebrowser/              # Python package
|   |-- main.py               # FastAPI app, router registration, static mount
|   |-- auth.py               # PAM auth, session token, require_auth dependency
|   |-- config.py             # Settings dataclass (reads env vars)
|   |-- routes/
|   |   |-- auth.py           # /api/auth/* (login, logout, me, cookie bridge)
|   |   |-- files.py          # /api/files/* (list, info, content, upload, mkdir, rename, delete)
|   |   +-- terminal.py       # /api/terminal WebSocket + PTY bridge
|   |-- services/
|   |   +-- filesystem.py     # Path validation (traversal prevention), file ops, type detection
|   +-- static/
|       |-- index.html        # SPA shell with ES import map (all CDN)
|       |-- css/styles.css    # Design tokens, light/dark mode
|       +-- js/
|           |-- app.js        # Frontend entry: auth check -> LoginForm or Layout
|           |-- api.js        # Fetch wrapper for backend API calls
|           |-- html.js       # HTM tagged template binding
|           |-- logger.js     # Named frontend logger (runtime level control)
|           |-- file-utils.js # Shared file-type utilities
|           |-- graphviz-svg.js  # In-browser DOT rendering helper
|           +-- components/   # 16 Preact components
|               |-- layout.js, tree.js, preview.js, code-editor.js,
|               |-- markdown-editor.js, editable-viewer.js,
|               |-- wysiwyg-editor.js, wysiwyg-bar.js, edit-bar.js,
|               |-- terminal.js, actions.js, breadcrumb.js,
|               |-- login.js, upload.js, command-palette.js,
|               +-- context-menu.js
|-- tests/                    # 14 test files (~109 tests, ~3,353 lines)
|-- deploy/                   # Shell-script deployment (see Deployment below)
|-- docs/                     # Architecture diagrams (DOT) + debugging guide
|-- pyproject.toml            # Package metadata, deps, pytest config
+-- uv.lock                   # Deterministic dependency lockfile
```

## Architecture Diagrams (DOT)

| File | What it shows |
|------|--------------|
| `docs/architecture.dot` | System layers: infrastructure, frontend components, backend routes, storage |
| `docs/auth-and-tls.dot` | Auth lifecycle, TLS tier diagram, frontdoor integration, WebSocket auth bypass |
| `docs/file-handling.dot` | File API endpoints, path validation chain, upload flow, error codes |
| `docs/preview-system.dot` | Three file-type mapping systems (backend, JS, CSS), data-flow pipeline, renderer components |

Render with Graphviz: `dot -Tsvg docs/architecture.dot -o docs/architecture.svg`

## Configuration Files

### Build and package

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, runtime deps (fastapi, uvicorn, python-pam, itsdangerous, python-multipart, six), dev deps (pytest, httpx), pytest config |
| `uv.lock` | Full transitive dependency lockfile |

### Deployment artifacts: `deploy/`

| File | Purpose |
|------|---------|
| `install.sh` | Full installer: FQDN detection, PAM setup, rsync, venv, Caddy install, 3-tier TLS (Tailscale > self-signed > HTTP), systemd unit, env file |
| `update.sh` | Incremental update: rsync + pip upgrade + systemctl restart |
| `filebrowser.service` | systemd unit template (`FILEBROWSER_USER`, `FILEBROWSER_DIR`, `FILEBROWSER_PORT` placeholders) |
| `filebrowser.caddy.template` | Caddy HTTPS config with `forward_auth` (frontdoor integration) + WebSocket bypass for `/api/terminal*` |
| `filebrowser.caddy.http.template` | Caddy HTTP fallback config (same routing, no TLS block) |

### Runtime config (generated at install, not committed)

| File | Location | Contents |
|------|----------|----------|
| `filebrowser.env` | `/opt/filebrowser/filebrowser.env` | `FILEBROWSER_SECRET_KEY`, `FILEBROWSER_SECURE_COOKIES`, `FILEBROWSER_LOG_LEVEL` (mode 0600) |
| `.port` | `/opt/filebrowser/.port` | Persisted internal uvicorn port |
| Caddy snippet | `/etc/caddy/conf.d/filebrowser.caddy` | Generated from template at install time |

### Dot files

| File | Purpose |
|------|---------|
| `.gitignore` | Ignores `__pycache__/`, `*.pyc/pyo`, `.venv/`, `dist/`, `*.egg-info/`, `.pytest_cache/`, `.discovery/` |

No `.env`, `.dockerignore`, `.eslintrc`, or CI config.

## Development Workflow

### Setup

```bash
cd filebrowser
uv sync                          # or: python -m venv .venv && pip install -e ".[dev]"
```

### Run locally

```bash
uv run uvicorn filebrowser.main:app --reload --host 0.0.0.0 --port 58080
```

App object: `filebrowser.main:app`

### Test

```bash
uv run pytest                    # 14 test files, ~109 tests, PAM always mocked
```

Tests cover: path traversal prevention, file operations, auth lifecycle, terminal WebSocket/PTY, config, routes, layout integration, preview security, context menu, action bar.

### Deploy to host

```bash
sudo deploy/install.sh           # first time (creates /opt/filebrowser, systemd, Caddy snippet)
sudo deploy/update.sh            # incremental update (rsync + restart)
```

## Key Architectural Decisions

**No-build frontend** -- All 16 Preact components use HTM tagged template literals loaded from `esm.sh` via an ES import map in `index.html`. No npm, no bundler, no transpiler. Heavy libraries (CodeMirror, Tiptap, xterm.js, d3-graphviz) are all CDN imports.

**Defense-in-depth path validation** -- `FilesystemService.validate_path()` strips leading `/`, resolves with `Path.resolve()`, asserts `resolved.relative_to(home_dir)`. Applied to every mutating operation. Blocks `../`, encoded traversals, and symlinks outside home.

**Dual-mode auth** -- Standalone: PAM login produces a signed session cookie. Behind frontdoor: Caddy `forward_auth` injects `X-Authenticated-User`, and the cookie bridge in `/api/auth/me` issues a session cookie for WebSocket auth (Caddy WebSocket limitation workaround).

**Terminal PTY via WebSocket** -- `routes/terminal.py` uses `os.fork()` + `execvp` to spawn a real PTY. The xterm.js frontend connects over WebSocket at `/api/terminal`. Terminal routes **bypass** Caddy `forward_auth` because Caddy 2.6 can't forward-auth WebSocket upgrades; auth is handled by session cookie validation in the WebSocket handler.

**systemd + Caddy, no Docker** -- Same deployment model as frontdoor. Caddy listens on port 8447 (external), reverse-proxies to uvicorn on an internal port. The `conf.d/` drop-in pattern means filebrowser doesn't own the global Caddyfile.

**Three file-type detection layers** -- Backend (`filesystem.py` MIME detection), frontend JS (`file-utils.js` extension mapping), and CSS (icon color-coding) each classify file types independently. The `docs/preview-system.dot` diagram maps all three.

## Relationship to frontdoor

filebrowser runs behind [frontdoor](../frontdoor)'s authentication gateway. The integration works through:

1. **Caddy `forward_auth`** -- Every HTTP request hits frontdoor's `/api/auth/validate` first
2. **`X-Authenticated-User` header** -- Caddy injects the verified username from frontdoor
3. **Cookie bridge** -- `/api/auth/me` converts the header into a filebrowser session cookie (needed for WebSocket auth)
4. **Shared conventions** -- Port allocation, cookie scoping, and auth patterns follow frontdoor's `context/conventions.md`

filebrowser is discoverable by frontdoor's service dashboard via its Caddy config in `/etc/caddy/conf.d/` and optional JSON manifest in `/opt/frontdoor/manifests/`.

## Existing Documentation

| File | Contents |
|------|----------|
| `README.md` | Feature list, UI layout, keyboard shortcuts, quick start, deployment, project structure, config, frontdoor integration, architecture diagram index, tech stack |
| `docs/debugging.md` | Backend logging levels, frontend logger API, component instrumentation table, journalctl commands |
| `docs/plans/` | Implementation plan documents for terminal features |