"""Terminal WebSocket endpoint — PTY bridge with auth and bidirectional I/O."""

import asyncio
import fcntl
import json
import logging
import os
import pty
import signal
import struct
import termios
import threading
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from filebrowser.auth import resolve_authenticated_user
from filebrowser.config import settings
from filebrowser.services.filesystem import validate_path_within

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


async def _authenticate_websocket(websocket: WebSocket) -> str | None:
    """Return the authenticated username or None."""
    result = resolve_authenticated_user(websocket.headers, websocket.cookies)
    logger.info(
        "WS auth: X-Authenticated-User=%r, session_cookie=%s, result=%r",
        websocket.headers.get("x-authenticated-user"),
        "present" if websocket.cookies.get("session") else "absent",
        result.username,
    )
    return result.username


def _resolve_cwd(path: str) -> Path | None:
    """Resolve *path* to an absolute directory inside home_dir.

    Returns None when:
    - The resolved path escapes home_dir (path traversal attempt).
    - The resolved path is not an existing directory.
    """
    home = Path(settings.home_dir).resolve()
    try:
        resolved = validate_path_within(path.lstrip("/"), home)
    except PermissionError:
        return None

    if not resolved.is_dir():
        return None

    return resolved


def _reap_child(pid: int) -> None:
    """Wait for *pid* to exit and reap it, preventing zombie processes.

    Called from a daemon thread so it does not block the event loop.
    """
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass  # Child was already reaped or never existed


async def _pty_to_ws(master_fd: int, websocket: WebSocket) -> None:
    """Read PTY output and forward it to the WebSocket as binary frames."""
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await loop.run_in_executor(None, os.read, master_fd, 4096)
            if not data:
                logger.info("PTY->WS: read returned empty bytes (PTY closed)")
                break
            await websocket.send_bytes(data)
    except OSError as e:
        logger.warning("PTY->WS: OSError: %s", e)
    except WebSocketDisconnect:
        logger.info("PTY->WS: WebSocket disconnected")
    except Exception as e:
        logger.exception("PTY->WS: unexpected error: %s", e)


async def _ws_to_pty(master_fd: int, websocket: WebSocket) -> None:
    """Read WebSocket messages and forward them to the PTY.

    JSON resize messages ``{"type": "resize", "cols": N, "rows": N}`` are
    handled via ``fcntl.ioctl``; all other data is written directly to the PTY.
    """
    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                logger.info("WS->PTY: client disconnected")
                break

            # Accept both text and binary frames
            if message.get("bytes") is not None:
                data: bytes = message["bytes"]
            elif message.get("text") is not None:
                data = message["text"].encode()
            else:
                continue

            # Check whether this is a resize control message
            if data[:1] == b"{":
                try:
                    msg = json.loads(data)
                    if isinstance(msg, dict) and msg.get("type") == "resize":
                        cols = int(msg.get("cols", 80))
                        rows = int(msg.get("rows", 24))
                        # struct 'H' format requires values in [0, 65535]; silently
                        # skip out-of-range dimensions rather than raising.
                        if not (0 <= cols <= 65535 and 0 <= rows <= 65535):
                            continue
                        winsize = struct.pack("HHHH", rows, cols, 0, 0)
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                        continue
                except (
                    json.JSONDecodeError,
                    ValueError,
                    UnicodeDecodeError,
                    struct.error,
                ):
                    pass

            os.write(master_fd, data)

    except WebSocketDisconnect:
        logger.info("WS->PTY: WebSocket disconnected")
    except OSError as e:
        logger.warning("WS->PTY: OSError: %s", e)
    except Exception as e:
        logger.exception("WS->PTY: unexpected error: %s", e)


@router.websocket("")
async def terminal_ws(websocket: WebSocket, path: str = "") -> None:
    """WebSocket terminal endpoint.

    Authentication → CWD resolution → accept → PTY + fork → bidirectional bridge.

    Close codes:
        4001  Unauthenticated
        4003  Invalid or out-of-bounds working directory
    """
    # --- Auth ---
    username = await _authenticate_websocket(websocket)
    if not username:
        logger.warning("Terminal WS: auth failed, closing with 4001")
        await websocket.close(code=4001)
        return

    # --- CWD ---
    cwd = _resolve_cwd(path)
    if cwd is None:
        logger.warning("Terminal WS: bad CWD path=%r, closing with 4003", path)
        await websocket.close(code=4003)
        return

    logger.info("Terminal WS: user=%s cwd=%s — accepting", username, cwd)

    # --- Accept ---
    await websocket.accept()

    # --- Spawn PTY ---
    master_fd, slave_fd = pty.openpty()
    logger.info("Terminal WS: PTY allocated master=%d slave=%d", master_fd, slave_fd)
    try:
        pid = os.fork()
    except OSError as e:
        logger.exception("Terminal WS: fork failed: %s", e)
        # Fork failed; close both FDs to avoid leaking them, then bail out.
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            os.close(slave_fd)
        except OSError:
            pass
        await websocket.close(code=1011)
        return

    if pid == 0:
        # Child process: set up controlling terminal, then exec the shell.
        os.close(master_fd)
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)
        os.chdir(str(cwd))
        shell = os.environ.get("SHELL", "/bin/bash")
        os.execvp(shell, [shell])
        os._exit(1)  # Unreachable; guards against execvp failure

    # Parent process: bridge I/O between WebSocket and PTY.
    os.close(slave_fd)
    logger.info("Terminal WS: forked child pid=%d, shell starting in %s", pid, cwd)

    # Check immediately if child is still alive
    try:
        wait_result = os.waitpid(pid, os.WNOHANG)
        if wait_result[0] != 0:
            logger.error(
                "Terminal WS: child pid=%d died immediately! status=%d",
                pid,
                wait_result[1],
            )
    except ChildProcessError:
        logger.error("Terminal WS: child pid=%d already reaped!", pid)

    t1 = asyncio.create_task(_pty_to_ws(master_fd, websocket))
    t2 = asyncio.create_task(_ws_to_pty(master_fd, websocket))

    logger.info("Terminal WS: bridge tasks started, waiting...")

    try:
        done, _ = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc:
                logger.error("Terminal WS: bridge task exception: %s", exc)
            else:
                logger.info(
                    "Terminal WS: bridge task completed normally: %s", task.get_name()
                )
    finally:
        logger.info("Terminal WS: cleaning up pid=%d", pid)
        t1.cancel()
        t2.cancel()
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError:
            pass
        # Reap the child in a background daemon thread so the event loop is
        # not blocked while waiting for the shell to exit.
        threading.Thread(target=_reap_child, args=(pid,), daemon=True).start()
        try:
            os.close(master_fd)
        except OSError:
            pass
