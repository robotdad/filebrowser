# filebrowser

Web-based remote file browser for headless Linux machines, accessible over Tailscale.

## What it does

- **Browse** -- tree-style navigation with color-coded file type icons, resizable sidebar, list/grid view toggle
- **Preview** -- text (line numbers), code (syntax-highlighted), rendered markdown, HTML (iframe with source toggle), images, audio, video, PDF
- **Manage** -- upload (drag-drop anywhere), download, rename, delete, create directories, batch operations (multi-select)
- **Search** -- command palette (Ctrl+K / Cmd+K) for quick file navigation across all expanded directories
- **Context menus** -- right-click any file or folder for quick actions (open, download, rename, copy path, delete)
- **Auth** -- PAM authentication using Linux user accounts, 30-day signed session cookies
- **Always on** -- systemd services, starts on boot, ~30MB RAM idle
- **Responsive** -- resizable two-panel layout on desktop, slide-out drawer on mobile
- **Light/dark mode** -- follows system preference, Apple HIG-inspired design

## Layout

```
+-----------------------------------------------------------+
|  Header: breadcrumb pills | [Search Cmd+K] | user | logout|
+-----------------+-----------------------------------------+
| [List|Grid] view|                                         |
|                 |      Preview Pane                       |
|  File Tree     ||                                         |
|  (resizable)   ||  Text: line numbers + content           |
|                ||  Code: syntax highlighted               |
|  color-coded   ||  Markdown: fully rendered               |
|  file icons    ||  HTML: iframe preview / source toggle   |
|                ||  Images: inline preview                 |
|  right-click   ||  Audio/Video: native player             |
|  for context   ||  PDF: embedded viewer                   |
|  menu          ||                                         |
+-----------------+-----------------------------------------+
|  Actions: upload | new folder | download | rename | delete|
|  (or batch toolbar when multi-selecting with Ctrl+click)  |
+-----------------------------------------------------------+
```

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+K / Cmd+K | Open command palette (file search) |
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
    auth.py                 # PAM auth + session management
    config.py               # Settings dataclass
    routes/
      auth.py               # /api/auth/* endpoints
      files.py              # /api/files/* endpoints
    services/
      filesystem.py         # Path validation, file ops, type detection
    static/
      index.html            # Single-page shell (CDN imports for Preact, fonts, icons)
      css/styles.css        # Design token system, light/dark mode
      js/
        app.js              # Entry point, auth routing
        api.js              # Fetch wrapper for backend API
        html.js             # HTM tagged template binding
        components/
          layout.js         # Main shell, resizable sidebar, drag-drop, keyboard shortcuts
          tree.js           # File tree with color-coded icons, grid view, multi-select
          preview.js        # Type-aware previewer (text, code, markdown, HTML, media, PDF)
          actions.js        # Action bar with batch toolbar mode
          breadcrumb.js     # Pill-shaped breadcrumb navigation
          login.js          # Login form
          upload.js         # Drag-drop upload modal
          command-palette.js # Cmd+K file search overlay
          context-menu.js   # Right-click context menu
  deploy/
    install.sh              # Automated deployment script
    filebrowser.service     # systemd unit template
    Caddyfile.template      # Caddy reverse proxy config
    tailscale-cert-renew.*  # Weekly cert renewal timer + service
  tests/
    test_filesystem.py      # Path traversal prevention, type detection
    test_auth.py            # Session creation/validation/expiry (PAM mocked)
    test_files.py           # API integration tests via TestClient
```

## Configuration

Settings are in `filebrowser/config.py`. Override via environment variables or by editing the dataclass defaults.

| Setting | Default | Description |
|---|---|---|
| `FILEBROWSER_SECRET_KEY` | Random (generated) | Signing key for session cookies. The install script persists one to `/opt/filebrowser/.secret_key`. |
| `session_timeout` | `2592000` (30 days) | Session cookie lifetime in seconds |
| `upload_max_size` | `1073741824` (1GB) | Maximum upload file size in bytes |
| `home_dir` | `Path.home()` | Root directory for file browsing |

The Caddy reverse proxy terminates HTTPS on port 443 using Tailscale certs stored in `/etc/ssl/tailscale/` and forwards to uvicorn on a random high port (assigned at install time, persisted in `/opt/filebrowser/.port`).

## Tech stack

**Backend** -- Python 3.11+, FastAPI, uvicorn, python-pam, itsdangerous, python-multipart

**Frontend** -- Preact + HTM (no build step), highlight.js (syntax), marked.js (markdown), Phosphor Icons, Inter + JetBrains Mono fonts, all via CDN

**Infrastructure** -- Caddy (reverse proxy / TLS), systemd (process management), Tailscale (network / certs)

5 Python runtime dependencies. 0 frontend build tools.
