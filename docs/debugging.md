# Debugging Filebrowser

## Backend Logging

Logging is configured at the top of `filebrowser/main.py` using `logging.basicConfig()` with `force=True` (overrides any prior config from third-party imports). The log level is read from the `FILEBROWSER_LOG_LEVEL` environment variable at startup and converted to a Python logging level.

### Configuration

| Setting | Value |
|---------|-------|
| Env var | `FILEBROWSER_LOG_LEVEL` |
| Default | `info` |
| Options | `debug`, `info`, `warning`, `error` |
| Format  | `%(asctime)s %(levelname)s %(name)s: %(message)s` |
| Output  | stderr → captured by journalctl under systemd |

To change the log level: edit the env file at the deployed location, then restart the service. The level is read once at startup — there's no hot-reload.

The `python_multipart` logger is pinned to INFO regardless of the app log level. This prevents multipart form parsing from flooding the journal when you run at DEBUG.

### Viewing Logs

```bash
# Live tail
journalctl -u filebrowser -f

# Recent logs (last 10 minutes)
journalctl -u filebrowser --since "10 min ago"

# Filter by severity
journalctl -u filebrowser | grep WARNING

# Filter by module
journalctl -u filebrowser | grep filebrowser.auth
```

### Log Level Guide

**DEBUG** — High-frequency tracing, suppressed at INFO and above:
- Auth flow details: frontdoor header checks, token validation steps
- Filesystem operations: directory listings, file reads, mkdir, rename
- Cookie bridge checks

**INFO** — Normal operational events (the default level):
- File reads and downloads (audit trail)
- File mutations: upload, mkdir, write, rename, delete
- Login success, logout
- Cookie bridge issuance
- App startup

**WARNING** — Security-relevant events. These always show at INFO and above:
- Path traversal attempts
- Auth failures: bad signatures, invalid tokens
- PAM authentication failures
- Login failures

**ERROR** — Application faults:
- Child process death in terminal sessions
- Bridge task exceptions

**EXCEPTION** — Unhandled exceptions with full tracebacks. The global exception handler in `main.py` catches anything that falls through and logs with `logger.exception()`, which includes the stack trace.

### What Gets Logged Where

| Logger name | Covers |
|-------------|--------|
| `filebrowser.auth` | PAM authentication, token validation, `require_auth` decisions |
| `filebrowser.services.filesystem` | Path traversal detection, file operations |
| `filebrowser.routes.files` | All file endpoint activity — reads, writes, permission errors |
| `filebrowser.routes.auth` | Login, logout, cookie bridge, auth checks |
| `filebrowser.routes.terminal` | Full PTY/WebSocket lifecycle |

## Frontend Logging

The frontend uses a shared logger module at `static/js/logger.js`. Each component creates a named logger that prefixes messages with `[ComponentName]` and gates output by level.

### Configuration

| Setting | Value |
|---------|-------|
| Default level | `warn` (debug and info are suppressed) |
| Available levels | `debug`, `info`, `warn`, `error`, `silent` |

To enable verbose output, open the browser DevTools console and run:

```javascript
window.__filebrowser_log_level('debug')
```

To go back to quiet mode:

```javascript
window.__filebrowser_log_level('warn')
```

To suppress everything:

```javascript
window.__filebrowser_log_level('silent')
```

### Instrumented Components

| Component | What it logs |
|-----------|-------------|
| **MarkdownEditor** | Mount lifecycle, save operations (path, size), save failures |
| **WysiwygEditor** | Mount/unmount lifecycle, editor creation |
| **CodeEditor** | Mount (path), language extension loading, load failures |
| **EditableViewer** | Mount (path, editing state), save operations, save failures |
| **Preview** | Render start (path, type), render complete, load failures |

### Adding Logging to New Components

```javascript
import { createLogger } from '../logger.js';
const log = createLogger('MyComponent');

// In component body:
log.debug('mount: path=%s', path);
log.info('action complete: path=%s', path);
log.warn('unexpected state: %s', detail);
log.error('operation failed', error);
```

The logger methods match `console.debug/info/warn/error` — they accept the same arguments including format strings and objects. Messages below the current level are silently dropped with no overhead beyond the function call.

## Useful Commands

```bash
# Live tail backend logs
journalctl -u filebrowser -f

# Recent logs
journalctl -u filebrowser --since "10 min ago"

# Filter by level
journalctl -u filebrowser | grep WARNING

# Filter by module
journalctl -u filebrowser | grep filebrowser.auth
```

```javascript
// Frontend: enable debug output in DevTools console
window.__filebrowser_log_level('debug')

// Frontend: back to default
window.__filebrowser_log_level('warn')
```
