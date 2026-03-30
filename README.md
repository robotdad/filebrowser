# filebrowser

Web-based remote file browser for headless Linux machines, accessible over Tailscale.

## What it does

- **Browse** -- tree-style navigation with color-coded file type icons, resizable sidebar, list/grid view toggle
- **Preview** -- text (line numbers), code (CodeMirror 6 syntax highlighting), rendered markdown, HTML (iframe with source toggle), DOT/Graphviz (in-browser rendering), images, audio, video, PDF
- **Edit** -- CodeMirror 6 code editor, WYSIWYG markdown editor (Tiptap v2) with View/Edit/Source tabs
- **Terminal** -- interactive shell via xterm.js + server-side PTY, dockable side or bottom panel, "Open Terminal Here" from context menu
- **Manage** -- upload (drag-drop anywhere), download, rename, delete, create directories, batch operations (multi-select)
- **Search** -- command palette (Ctrl+K / Cmd+K) for quick file navigation across all expanded directories
- **Context menus** -- right-click any file or folder for quick actions (open, download, rename, copy path, open terminal here, delete)
- **Auth** -- PAM authentication using Linux user accounts, 30-day signed session cookies; integrates with [frontdoor](https://github.com/robotdad/frontdoor) for shared SSO via `X-Authenticated-User` header
- **Always on** -- systemd services, starts on boot, ~30MB RAM idle
- **Responsive** -- resizable two-panel layout on desktop, slide-out drawer on mobile
- **Light/dark mode** -- follows system preference, Apple HIG-inspired design

## Layout

```
+-----------------------------------------------------------+
|  Header: hostname | [Search Cmd+K] | [Terminal] | user    |
+-----------------+-----------------------------------------+
| [List|Grid] view|                                         |
|                 |      Preview / Edit Pane                 |
|  File Tree     ||                                         |
|  (resizable)   ||  Text: line numbers + content           |
|                ||  Code: CodeMirror 6 editor              |
|  color-coded   ||  Markdown: View / Edit (WYSIWYG) / Src  |
|  file icons    ||  HTML: iframe preview / source toggle   |
|                ||  DOT: in-browser Graphviz rendering     |
|  right-click   ||  Images: inline preview                 |
|  for context   ||  Audio/Video: native player             |
|  menu          ||  PDF: embedded viewer                   |
|                 +-----------------------------------------+
|                 |  Terminal (xterm.js + PTY)               |
|                 |  dockable: side or bottom panel          |
+-----------------+-----------------------------------------+
|  Actions: upload | new folder | download | rename | delete|
|  (or batch toolbar when multi-selecting with Ctrl+click)  |
+-----------------------------------------------------------+
```

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+K / Cmd+K | Open command palette (file search) |
| Ctrl+` | Toggle terminal panel |
| Ctrl+click / Cmd+click | Multi-select files for batch operations |
| Right-click | Context menu on files and folders |
| Escape | Close command palette, context menu, or modal |
| Arrow keys + Enter | Navigate command palette results |

## Quick start (remote dev)

Requires Python 3.11+ on a Linux box. This is designed for headless machines you connect to over the network.

```bash
git clone https://github.com/robotdad/filebrowser.git && cd filebrowser
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn filebrowser.main:app --reload --host 0.0.0.0 --port 58080
```

Open `http://<hostname>:58080` from any machine that can reach it (the production install uses a random high port behind Caddy). Login uses PAM, so provide your Linux user credentials.

**PAM requires read access to `/etc/shadow`.** Add your user to the `shadow` group:

```bash
sudo usermod -aG shadow $(whoami)
```

Log out and back in (or start a new shell) for the group change to take effect.

Note: PAM auth does not work on macOS -- use a Linux box or skip straight to deployment.

Run tests:

```bash
pytest
```

109 tests covering path traversal prevention, auth, and file operations.

## Deployment

Target machines: headless Linux boxes on a Tailscale network (tested on DGX Spark and Raspberry Pi 4).

```bash
git clone https://github.com/robotdad/filebrowser.git /tmp/filebrowser
sudo /tmp/filebrowser/deploy/install.sh
```

`install.sh` does the following:

1. Detects the Tailscale FQDN via `tailscale status --json`
2. Adds your user to the `shadow` group (required for PAM auth)
3. Copies the project to `/opt/filebrowser`
4. Creates a virtualenv and installs dependencies
5. Attempts Tailscale/Let's Encrypt TLS certificate generation (requires paid Tailscale plan)
6. Installs Caddy (if not present) and writes the Caddyfile
7. Writes, enables, and **restarts** both `filebrowser` and `caddy` systemd services

If TLS cert generation fails (free Tailscale plan), the script falls back to plain HTTP on port 80. Tailscale's WireGuard tunnel already encrypts traffic between your devices, so HTTP inside your tailnet is safe.

After install, browse to `http://<hostname>/` (or `https://` if you have a paid plan) from any device on the tailnet.

Check status:

```bash
sudo systemctl status filebrowser
sudo systemctl status caddy
```

## Project structure

```
filebrowser/
  filebrowser/
    main.py                 # FastAPI app, static mount, error handler
    auth.py                 # PAM auth, session mgmt, frontdoor integration
    config.py               # Settings dataclass
    routes/
      auth.py               # /api/auth/* endpoints + cookie bridge
      files.py              # /api/files/* endpoints
      terminal.py           # /api/terminal WebSocket + PTY bridge
    services/
      filesystem.py         # Path validation, file ops, type detection
    static/
      index.html            # Single-page shell (CDN imports for Preact, fonts, icons)
      css/styles.css        # Design token system, light/dark mode
      js/
        app.js              # Entry point, auth routing
        api.js              # Fetch wrapper for backend API
        html.js             # HTM tagged template binding
        graphviz-svg.js     # In-browser DOT file rendering (@viz-js/viz)
        components/
          layout.js         # Main shell, resizable sidebar, terminal panel
          tree.js           # File tree with color-coded icons, grid view, multi-select
          preview.js        # Type-aware previewer (text, code, markdown, HTML, DOT, media, PDF)
          code-editor.js    # CodeMirror 6 syntax-highlighted editor
          markdown-editor.js # Markdown with View/Edit(WYSIWYG)/Source tabs
          terminal.js       # xterm.js WebSocket terminal component
          actions.js        # Action bar with batch toolbar and terminal toggle
          breadcrumb.js     # Pill-shaped breadcrumb navigation
          login.js          # Login form
          upload.js         # Drag-drop upload modal
          command-palette.js # Cmd+K file search overlay
          context-menu.js   # Right-click context menu + "Open Terminal Here"
  deploy/
    install.sh              # Automated deployment script
    filebrowser.service     # systemd unit template
    filebrowser.caddy.template  # Caddy HTTPS config (with forward_auth)
    filebrowser.caddy.http.template  # Caddy HTTP fallback config
  docs/
    architecture.dot        # System architecture diagram
    auth-and-tls.dot        # Auth lifecycle + TLS + frontdoor integration
    file-handling.dot       # File operations flow
    preview-system.dot      # Preview subsystem + renderer routing
  tests/
    test_filesystem.py      # Path traversal prevention, type detection
    test_auth.py            # Session creation/validation/expiry (PAM mocked)
    test_files.py           # API integration tests via TestClient
    test_terminal.py        # Terminal WebSocket + PTY tests
```

## Configuration

Settings are in `filebrowser/config.py`. Override via environment variables or by editing the dataclass defaults.

| Setting | Default | Description |
|---|---|---|
| `FILEBROWSER_SECRET_KEY` | Random (generated) | Signing key for session cookies. The install script persists one to `/opt/filebrowser/.secret_key`. |
| `session_timeout` | `2592000` (30 days) | Session cookie lifetime in seconds |
| `upload_max_size` | `1073741824` (1GB) | Maximum upload file size in bytes |
| `home_dir` | `Path.home()` | Root directory for file browsing |
| `FILEBROWSER_TERMINAL_ENABLED` | `true` | Enable/disable the terminal feature |
| `FILEBROWSER_LOG_LEVEL` | `info` | Log verbosity: debug, info, warning, error |

The Caddy reverse proxy terminates HTTPS on port 443 using Tailscale certs stored in `/etc/ssl/tailscale/` and forwards to uvicorn on a random high port (assigned at install time, persisted in `/opt/filebrowser/.port`).

## Frontdoor integration

filebrowser is designed to work with [frontdoor](https://github.com/robotdad/frontdoor), a shared authentication gateway. When deployed behind frontdoor:

- Caddy's `forward_auth` validates every HTTP request through frontdoor, which injects the `X-Authenticated-User` header
- filebrowser trusts this header and skips its own login flow
- The terminal WebSocket (`/api/terminal`) bypasses `forward_auth` due to a Caddy 2.6 limitation with WebSocket upgrades
- A cookie bridge in `/api/auth/me` issues a filebrowser session cookie when frontdoor identity is detected, enabling WebSocket auth

filebrowser works standalone without frontdoor -- it falls back to its own PAM login and session cookies.

## Architecture diagrams

The `docs/` directory contains DOT/Graphviz architecture diagrams. These are the source of truth for system design -- no rendered images are committed. View them with `dot -Tsvg <file>.dot` or a live Graphviz preview extension.

| Diagram | What it covers |
|---------|---------------|
| `docs/architecture.dot` | System layers: infrastructure, frontend components, backend routes, storage |
| `docs/auth-and-tls.dot` | Auth lifecycle, TLS tiers, frontdoor integration, WebSocket auth bypass |
| `docs/file-handling.dot` | File API endpoints, path validation chain, upload flow, error codes |
| `docs/preview-system.dot` | Three file-type mapping systems, data flow pipeline, renderer components |

## Tech stack

**Backend** -- Python 3.11+, FastAPI, uvicorn, python-pam, itsdangerous, python-multipart

**Frontend** -- Preact + HTM (no build step), CodeMirror 6 (code editing), Tiptap v2 (WYSIWYG markdown), xterm.js (terminal), @viz-js/viz (DOT rendering), marked.js (markdown preview), Phosphor Icons, Inter + JetBrains Mono fonts, all via CDN

**Infrastructure** -- Caddy (reverse proxy / TLS), systemd (process management), Tailscale (network / certs)

5 Python runtime dependencies. 0 frontend build tools.
