# filebrowser

Web-based remote file browser for headless Linux machines, accessible over Tailscale.

## What it does

- **Browse** -- tree-style navigation of the filesystem rooted at `$HOME`
- **Preview** -- text (with line numbers), code (syntax-highlighted), rendered markdown, images, audio, video, PDF
- **Manage** -- upload, download, rename, delete, create directories
- **Auth** -- PAM authentication using Linux user accounts, signed session cookies
- **Always on** -- systemd services, starts on boot, ~30MB RAM idle
- **Responsive** -- two-panel layout on desktop, slide-out drawer on mobile
- **Light/dark mode** -- follows system preference

## Layout

```
+---------------------------------------------------+
|  Header: breadcrumb path  |  user  |  logout      |
+---------------+-----------------------------------+
|               |                                   |
|  File Tree    |      Preview Pane                 |
|  (sidebar)    |                                   |
|               |  Text: line numbers + content     |
|  folders/     |  Code: syntax highlighted         |
|    files      |  Markdown: rendered HTML           |
|               |  Images: inline preview            |
|               |  Audio/Video: native player        |
|               |                                   |
+---------------+-----------------------------------+
|  Actions: upload | new folder | rename | delete   |
+---------------------------------------------------+
```

## Quick start (remote dev)

Requires Python 3.11+ on a Linux box. This is designed for headless machines you connect to over the network.

```bash
git clone https://github.com/robotdad/filebrowser.git && cd filebrowser
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn filebrowser.main:app --reload --host 0.0.0.0
```

Open `http://<hostname>:8000` from any machine that can reach it. Login uses PAM, so provide your Linux user credentials.

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
2. Copies the project to `/opt/filebrowser`
3. Creates a virtualenv and installs dependencies
4. Generates a Tailscale/Let's Encrypt TLS certificate
5. Installs Caddy (if not present) and writes the Caddyfile
6. Writes and enables systemd units (`filebrowser.service`, `caddy`, cert renewal timer)

After install, browse to `https://<hostname>/` from any device on the tailnet.

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
      index.html            # Single-page shell
      css/styles.css        # Light/dark mode via CSS custom properties
      js/
        app.js              # Entry point, auth routing
        api.js              # Fetch wrapper for backend API
        components/         # Preact components (login, tree, preview, etc.)
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
| `session_timeout` | `86400` (24h) | Session cookie lifetime in seconds |
| `upload_max_size` | `1073741824` (1GB) | Maximum upload file size in bytes |
| `home_dir` | `Path.home()` | Root directory for file browsing |

The Caddy reverse proxy terminates HTTPS on port 443 using Tailscale certs stored in `/etc/ssl/tailscale/` and forwards to uvicorn on `localhost:8000`.

## Tech stack

**Backend** -- Python 3.11+, FastAPI, uvicorn, python-pam, itsdangerous, python-multipart

**Frontend** -- Preact + HTM (no build step), highlight.js (syntax), marked.js (markdown), all via CDN

**Infrastructure** -- Caddy (reverse proxy / TLS), systemd (process management), Tailscale (network / certs)

5 Python runtime dependencies. 0 frontend build tools.
