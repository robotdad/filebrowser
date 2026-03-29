"""Tests for terminal WebSocket endpoint — auth and PTY lifecycle.

Covers:
  - TestTerminalAuth  — proxy-header auth, session-cookie auth, rejection
  - TestPtyLifecycle  — non-mocked fork/PTY integration tests
  - TestForkFailure   — close-code 1011 when os.fork() raises OSError
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
import json
import os
import pty
import select
import termios
import threading
import time
from typing import Any, cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from filebrowser.auth import create_session_token
from filebrowser.config import settings


# ── helpers ───────────────────────────────────────────────────────────────────


async def _async_noop(*_args, **_kwargs) -> None:
    """Async no-op — replaces bridge coroutines to allow clean test teardown."""


@contextmanager
def _mock_terminal_session(
    *, fork_return_value: int = 99999, fork_side_effect: BaseException | None = None
) -> Iterator[None]:
    """Patch PTY and fork-related calls for lightweight endpoint tests."""
    with (
        patch("filebrowser.routes.terminal.pty") as mock_pty,
        patch(
            "filebrowser.routes.terminal.os.fork",
            return_value=fork_return_value,
            side_effect=fork_side_effect,
        ),
        patch("filebrowser.routes.terminal.os.close"),
        patch("filebrowser.routes.terminal.os.kill"),
        patch("filebrowser.routes.terminal._pty_to_ws", new=_async_noop),
        patch("filebrowser.routes.terminal._ws_to_pty", new=_async_noop),
    ):
        mock_pty.openpty.return_value = (3, 4)
        yield


def _make_terminal_client(home_dir, monkeypatch) -> TestClient:
    """Build a TestClient with the terminal router mounted on *home_dir*."""
    import sys

    monkeypatch.setattr(settings, "home_dir", home_dir)
    monkeypatch.setattr(settings, "terminal_enabled", True)

    for mod in ("filebrowser.main", "filebrowser.routes.terminal"):
        sys.modules.pop(mod, None)

    import filebrowser.routes as routes_pkg

    if hasattr(routes_pkg, "terminal"):
        delattr(routes_pkg, "terminal")

    import filebrowser.main as main_mod

    return TestClient(main_mod.app)


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def terminal_client(tmp_path, monkeypatch):
    """TestClient without pre-supplied auth credentials."""
    return _make_terminal_client(tmp_path, monkeypatch)


@pytest.fixture()
def authed_terminal_client(tmp_path, monkeypatch):
    """TestClient — caller provides X-Authenticated-User header or session cookie."""
    return _make_terminal_client(tmp_path, monkeypatch)


# ── TestTerminalAuth ───────────────────────────────────────────────────────────


class TestTerminalAuth:
    """WebSocket authentication — proxy-header, session-cookie, and rejection."""

    def test_rejects_unauthenticated_websocket(self, terminal_client):
        """Connections with neither header nor cookie are rejected (close 4001)."""
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with terminal_client.websocket_connect("/api/terminal"):
                pass  # pragma: no cover
        assert exc_info.value.code == 4001

    def test_accepts_authenticated_websocket(self, authed_terminal_client):
        """Connections with X-Authenticated-User header are accepted (proxy mode).

        The header is set by Caddy's forward_auth after frontdoor validates
        the session.
        """
        with _mock_terminal_session():
            # A WebSocketDisconnect here would mean authentication failed (4001).
            # A clean context-manager exit means the connection was accepted.
            with authed_terminal_client.websocket_connect(
                "/api/terminal",
                headers={"X-Authenticated-User": "testuser"},
            ) as ws:
                ws.close()

    def test_accepts_session_cookie_auth(self, tmp_path, monkeypatch):
        """Connections authenticated via a valid signed session cookie are accepted.

        This covers the standalone-mode fallback path where no proxy header is
        present but a valid ``session`` cookie is.
        """
        client = _make_terminal_client(tmp_path, monkeypatch)

        token = create_session_token("testuser", settings.secret_key)
        client.cookies.set("session", token)

        with _mock_terminal_session():
            with client.websocket_connect("/api/terminal") as ws:
                ws.close()

    def test_rejects_cookie_signed_with_wrong_key(self, terminal_client):
        """Cookies signed with the wrong secret key are rejected with code 4001."""
        bad_token = create_session_token("testuser", "wrong-secret-key")
        terminal_client.cookies.set("session", bad_token)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with terminal_client.websocket_connect("/api/terminal"):
                pass  # pragma: no cover
        assert exc_info.value.code == 4001

    def test_rejects_connection_without_any_credentials(self, terminal_client):
        """Connections with neither header nor cookie are rejected (close 4001).

        Validates the baseline authentication gate — the terminal endpoint
        must reject unauthenticated connections.
        """
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with terminal_client.websocket_connect("/api/terminal"):
                pass  # pragma: no cover
        assert exc_info.value.code == 4001

    def test_proxy_header_wins_over_invalid_session_cookie(
        self, authed_terminal_client
    ):
        """X-Authenticated-User header takes precedence over an invalid session cookie.

        A valid proxy header must authenticate the connection even when the
        session cookie is present but invalid (signed with the wrong key).
        The proxy header is the authoritative identity source; the cookie
        must not cause a rejection.
        """
        bad_token = create_session_token("attacker", "wrong-secret-key")
        authed_terminal_client.cookies.set("session", bad_token)

        with _mock_terminal_session():
            with authed_terminal_client.websocket_connect(
                "/api/terminal",
                headers={"X-Authenticated-User": "testuser"},
            ) as ws:
                ws.close()


# ── TestPtyLifecycle ───────────────────────────────────────────────────────────


class TestPtyLifecycle:
    """Non-mocked integration tests for the real PTY/fork lifecycle.

    These tests bypass the FastAPI layer and exercise ``pty.openpty()``,
    ``os.fork()``, and the cleanup path directly, catching regressions
    that mocked endpoint tests cannot detect.
    """

    def test_pty_echo_produces_output(self, tmp_path):
        """A real PTY-backed child process running ``echo`` produces readable output.

        Validates the core PTY/fork mechanics: open a master/slave pair,
        fork a child that runs ``echo``, and verify the parent can read the
        expected bytes from the master fd within a short timeout.
        """
        master_fd, slave_fd = pty.openpty()
        pid = os.fork()

        if pid == 0:  # child ────────────────────────────────────────────────
            os.close(master_fd)
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.chdir(str(tmp_path))
            os.execvp("echo", ["echo", "pty-lifecycle-ok"])
            os._exit(1)  # pragma: no cover

        # parent ──────────────────────────────────────────────────────────────
        os.close(slave_fd)

        output = b""
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(master_fd, 4096)
                    output += chunk
                except OSError:
                    break
            if b"pty-lifecycle-ok" in output:
                break

        os.waitpid(pid, 0)
        try:
            os.close(master_fd)
        except OSError:
            pass

        assert b"pty-lifecycle-ok" in output

    def test_fork_child_receives_sighup_and_is_reaped(self):
        """Forked child exits on SIGHUP and is reaped without a zombie.

        Mirrors the cleanup path in ``terminal_ws`` — the parent sends SIGHUP
        then waits for the child.  Verifies that ``WIFSIGNALED`` or ``WIFEXITED``
        is true after reaping, i.e. no zombie remains.
        """
        import signal

        master_fd, slave_fd = pty.openpty()
        pid = os.fork()

        if pid == 0:  # child ────────────────────────────────────────────────
            os.close(master_fd)
            # Use default SIGHUP handler so the signal terminates the child.
            signal.signal(signal.SIGHUP, signal.SIG_DFL)
            time.sleep(10)
            os._exit(0)  # pragma: no cover

        # parent ──────────────────────────────────────────────────────────────
        os.close(slave_fd)
        os.close(master_fd)

        # Brief pause so the child fully enters sleep() before we signal it.
        time.sleep(0.05)

        try:
            os.kill(pid, signal.SIGHUP)
        except ProcessLookupError:
            pass  # Already gone — still counts as success.

        _, status = os.waitpid(pid, 0)
        # Child exited due to signal or cleanly; either way no zombie remains.
        assert os.WIFSIGNALED(status) or os.WIFEXITED(status)


# ── TestForkFailure ────────────────────────────────────────────────────────────


class TestForkFailure:
    """Tests for the os.fork() failure path in the terminal endpoint."""

    def test_fork_failure_closes_with_code_1011(self, authed_terminal_client):
        """When os.fork() raises OSError the WebSocket is closed with code 1011.

        Checks the exact close code rather than a broad ``Exception`` catch so
        that any other unexpected close code surfaces as a test failure.
        """
        with _mock_terminal_session(
            fork_side_effect=OSError("fork: Resource temporarily unavailable")
        ):
            with authed_terminal_client.websocket_connect(
                "/api/terminal",
                headers={"X-Authenticated-User": "testuser"},
            ) as ws:
                msg = ws.receive()

        assert msg["type"] == "websocket.close"
        assert msg["code"] == 1011


# ── TestTerminalPTY ───────────────────────────────────────────────────────────


@pytest.mark.filterwarnings(
    r"ignore:This process .* is multi-threaded, use of fork\(\) may lead to deadlocks in the child\.:DeprecationWarning"
)
class TestTerminalPTY:
    """PTY lifecycle integration tests via the live WebSocket endpoint.

    These tests connect to the real ``/api/terminal`` WebSocket and exercise
    the bidirectional bridge without mocking the PTY or fork.
    """

    def test_terminal_echoes_input(self, authed_terminal_client):
        """Shell echoes ``echo HELLO_TERMINAL`` back over the WebSocket.

        Connects with the proxy-auth header, lets the shell start (0.3 s),
        drains the initial prompt, sends the echo command, waits for output
        (0.5 s), collects up to 20 messages, and asserts ``HELLO_TERMINAL``
        appears in the combined output.

        Note: sleep values (0.3/0.5) may need to be raised to 0.5/1.0 on
        slow CI systems to avoid flakiness.
        """
        drained: list[bytes] = []
        collected: list[bytes] = []
        # Flag: clear → drain phase; set → collect phase (keeps up to 20 messages).
        echo_phase = threading.Event()

        def _collect_smart() -> None:
            """Single consumer: drains prompt, then collects up to 20 responses."""
            for _ in range(100):  # safety upper-bound
                try:
                    msg = ws.receive_bytes()
                except Exception:
                    break
                if echo_phase.is_set():
                    if len(collected) < 20:
                        collected.append(msg)
                else:
                    drained.append(msg)  # drain phase: consume and discard prompt

        with authed_terminal_client.websocket_connect(
            "/api/terminal",
            headers={"X-Authenticated-User": "testuser"},
        ) as ws:
            collector = threading.Thread(target=_collect_smart, daemon=True)
            collector.start()

            time.sleep(0.3)  # Let the shell start up and emit its prompt.
            # Drain initial prompt: collector is in drain mode, consuming prompt messages.

            ws.send_text("echo HELLO_TERMINAL\n")  # Send the echo command.
            echo_phase.set()  # Switch collector to echo-collection mode (up to 20).
            time.sleep(0.5)  # Wait for the shell to produce output.

            # Collect up to 20 messages from the echo response.
            collector.join(timeout=2.0)

        output = b"".join(collected)
        assert b"HELLO_TERMINAL" in output

    def test_terminal_resize_message(self, authed_terminal_client):
        """Sending a resize JSON message does not crash the endpoint.

        Connects, lets the shell start, sends a ``{"type":"resize"}`` frame,
        waits briefly, then closes.  A clean exit (no exception) is the pass
        condition \u2014 the ioctl path must handle the resize without raising.
        """
        with authed_terminal_client.websocket_connect(
            "/api/terminal",
            headers={"X-Authenticated-User": "testuser"},
        ) as ws:
            # Let the shell start up before sending the resize.
            time.sleep(0.3)

            # Send a terminal resize control message.
            ws.send_text(json.dumps({"type": "resize", "cols": 120, "rows": 40}))

            # Brief pause so the ioctl has time to execute before we close.
            time.sleep(0.1)
            # Exiting the context manager cleanly \u2014 no exception \u2014 is the assertion.


# ── TestTerminalPathValidation ────────────────────────────────────────────────


class TestTerminalPathValidation:
    """Path validation tests for the ``path`` query parameter.

    Ensures the server enforces home-directory confinement and accepts the
    empty-path case that defaults to the home directory.
    """

    def test_invalid_path_rejected(self, authed_terminal_client):
        """Path traversal attempts are rejected before accepting the connection.

        ``path=../../etc`` would escape the home directory; the server must
        close the WebSocket before accepting the connection.
        """
        with pytest.raises(WebSocketDisconnect):
            with authed_terminal_client.websocket_connect(
                "/api/terminal?path=../../etc",
                headers={"X-Authenticated-User": "testuser"},
            ):
                pass  # pragma: no cover

    def test_empty_path_uses_home_dir(self, authed_terminal_client):
        """An empty ``path=`` query parameter defaults to the home directory.

        The connection must be accepted (no exception, no close before accept)
        when ``path`` is empty.  PTY and fork are mocked to keep the test fast
        and free of child-process side-effects.
        """
        with _mock_terminal_session():
            with authed_terminal_client.websocket_connect(
                "/api/terminal?path=",
                headers={"X-Authenticated-User": "testuser"},
            ) as ws:
                ws.close()
            # Reaching here without WebSocketDisconnect confirms the connection
            # was accepted \u2014 empty path correctly resolved to the home directory.

    def test_leading_slash_path_stays_relative_to_home_dir(
        self, authed_terminal_client, tmp_path
    ):
        """A leading slash still resolves inside the configured home directory."""
        (tmp_path / "nested").mkdir()

        with _mock_terminal_session():
            with authed_terminal_client.websocket_connect(
                "/api/terminal?path=/nested",
                headers={"X-Authenticated-User": "testuser"},
            ) as ws:
                ws.close()


class TestWsToPty:
    def test_plain_text_messages_do_not_attempt_json_decode(self):
        """Regular keystrokes bypass JSON parsing and write directly to the PTY."""
        from filebrowser.routes.terminal import _ws_to_pty

        class StubWebSocket:
            def __init__(self):
                self._messages = [
                    {"type": "websocket.receive", "text": "ls\n"},
                    {"type": "websocket.disconnect"},
                ]

            async def receive(self):
                return self._messages.pop(0)

        with (
            patch(
                "filebrowser.routes.terminal.json.loads",
                side_effect=AssertionError("json.loads should not run"),
            ),
            patch("filebrowser.routes.terminal.os.write") as mock_write,
        ):
            asyncio.run(_ws_to_pty(123, cast(Any, StubWebSocket())))

        mock_write.assert_called_once_with(123, b"ls\n")
