import asyncio
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from filebrowser.routes.auth import router as auth_router

SECRET = "test-secret-key-for-unit-tests"


class TestCreateSessionToken:
    def test_returns_string(self):
        from filebrowser.auth import create_session_token

        token = create_session_token("testuser", SECRET)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_contains_username(self):
        from filebrowser.auth import create_session_token

        token = create_session_token("alice", SECRET)
        assert "alice" in token

    def test_different_users_get_different_tokens(self):
        from filebrowser.auth import create_session_token

        t1 = create_session_token("alice", SECRET)
        t2 = create_session_token("bob", SECRET)
        assert t1 != t2


class TestValidateSessionToken:
    def test_valid_token_returns_username(self):
        from filebrowser.auth import create_session_token, validate_session_token

        token = create_session_token("alice", SECRET)
        result = validate_session_token(token, SECRET, max_age=3600)
        assert result == "alice"

    def test_wrong_secret_returns_none(self):
        from filebrowser.auth import create_session_token, validate_session_token

        token = create_session_token("alice", SECRET)
        result = validate_session_token(token, "wrong-secret", max_age=3600)
        assert result is None

    def test_tampered_token_returns_none(self):
        from filebrowser.auth import create_session_token, validate_session_token

        token = create_session_token("alice", SECRET)
        tampered = token[:-5] + "XXXXX"
        result = validate_session_token(tampered, SECRET, max_age=3600)
        assert result is None

    def test_garbage_token_returns_none(self):
        from filebrowser.auth import validate_session_token

        result = validate_session_token("not.a.valid.token", SECRET, max_age=3600)
        assert result is None

    def test_empty_token_returns_none(self):
        from filebrowser.auth import validate_session_token

        result = validate_session_token("", SECRET, max_age=3600)
        assert result is None


class TestTokenExpiry:
    def test_expired_token_returns_none(self):
        import time
        from filebrowser.auth import create_session_token, validate_session_token

        token = create_session_token("alice", SECRET)
        time.sleep(1.1)  # itsdangerous uses second-resolution timestamps
        result = validate_session_token(token, SECRET, max_age=0)
        assert result is None


class TestAuthenticatePam:
    def test_pam_function_exists(self):
        from filebrowser.auth import authenticate_pam

        assert callable(authenticate_pam)

    def test_pam_mock_success(self):
        from filebrowser.auth import authenticate_pam

        with patch("filebrowser.auth.pam.pam") as mock_pam_class:
            mock_pam_class.return_value.authenticate.return_value = True
            assert authenticate_pam("user", "pass") is True

    def test_pam_mock_failure(self):
        from filebrowser.auth import authenticate_pam

        with patch("filebrowser.auth.pam.pam") as mock_pam_class:
            mock_pam_class.return_value.authenticate.return_value = False
            assert authenticate_pam("user", "wrong") is False


class TestRequireAuth:
    def test_missing_cookie_raises_401(self):
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert exc_info.value.status_code == 401

    def test_invalid_cookie_raises_401(self):
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.headers = {}
        request.cookies = {"session": "garbage-token"}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert exc_info.value.status_code == 401

    def test_valid_cookie_still_works_without_remote_user(self):
        from filebrowser.auth import require_auth, create_session_token

        token = create_session_token("alice", SECRET)
        request = MagicMock()
        request.headers = {}
        request.cookies = {"session": token}
        with patch("filebrowser.auth.settings") as mock_settings:
            mock_settings.secret_key = SECRET
            mock_settings.session_timeout = 3600
            result = asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert result == "alice"


class TestRequireAuthWithRemoteUser:
    def test_remote_user_header_bypasses_cookie(self):
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.headers = {"X-Authenticated-User": "alice"}
        request.cookies = {}
        result = asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert result == "alice"

    def test_remote_user_takes_precedence_over_session_cookie(self):
        from filebrowser.auth import require_auth, create_session_token

        token = create_session_token("bob", SECRET)
        request = MagicMock()
        request.headers = {"X-Authenticated-User": "alice"}
        request.cookies = {"session": token}
        result = asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert result == "alice"

    def test_empty_remote_user_header_falls_back_to_session_cookie(self):
        from filebrowser.auth import require_auth, create_session_token

        token = create_session_token("bob", SECRET)
        request = MagicMock()
        request.headers = {"X-Authenticated-User": ""}
        request.cookies = {"session": token}
        with patch("filebrowser.auth.settings") as mock_settings:
            mock_settings.secret_key = SECRET
            mock_settings.session_timeout = 3600
            result = asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert result == "bob"

    def test_no_remote_user_no_cookie_raises_401(self):
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert exc_info.value.status_code == 401


class TestGetAuthSource:
    def test_returns_frontdoor_when_remote_user_present(self):
        from filebrowser.auth import get_auth_source

        request = MagicMock()
        request.headers = {"X-Authenticated-User": "alice"}
        assert get_auth_source(request) == "frontdoor"

    def test_returns_session_when_no_remote_user(self):
        from filebrowser.auth import get_auth_source

        request = MagicMock()
        request.headers = {}
        assert get_auth_source(request) == "session"

    def test_returns_session_when_remote_user_is_empty_string(self):
        from filebrowser.auth import get_auth_source

        request = MagicMock()
        request.headers = {"X-Authenticated-User": ""}
        assert get_auth_source(request) == "session"


# --- Route Tests ---


@pytest.fixture
def auth_client():
    app = FastAPI()
    app.include_router(auth_router)
    with TestClient(app, base_url="https://testserver") as c:
        yield c


class TestLoginRoute:
    def test_login_success(self, auth_client):
        with patch("filebrowser.routes.auth.authenticate_pam", return_value=True):
            response = auth_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "testpass"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["terminal_enabled"] is True
        assert "session" in response.cookies

    def test_login_failure(self, auth_client):
        with patch("filebrowser.routes.auth.authenticate_pam", return_value=False):
            response = auth_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "wrong"},
            )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "AUTH_FAILED"

    def test_login_missing_fields(self, auth_client):
        response = auth_client.post("/api/auth/login", json={})
        assert response.status_code == 422


class TestLogoutRoute:
    def test_logout_clears_cookie(self, auth_client):
        response = auth_client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["auth_source"] == "session"


class TestLogoutRouteAuthSource:
    def test_logout_returns_frontdoor_auth_source_when_remote_user_present(
        self, auth_client
    ):
        response = auth_client.post(
            "/api/auth/logout", headers={"X-Authenticated-User": "alice"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["auth_source"] == "frontdoor"

    def test_logout_returns_session_auth_source_in_standalone_mode(self, auth_client):
        response = auth_client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json()["auth_source"] == "session"


class TestMeRoute:
    def test_me_with_valid_session(self, auth_client):
        with patch("filebrowser.routes.auth.authenticate_pam", return_value=True):
            auth_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "testpass"},
            )
        response = auth_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["auth_source"] == "session"

    def test_me_without_session(self, auth_client):
        response = auth_client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_with_invalid_session(self, auth_client):
        auth_client.cookies.set("session", "invalid-token")
        response = auth_client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_with_remote_user_header_returns_frontdoor_source(self, auth_client):
        response = auth_client.get(
            "/api/auth/me", headers={"X-Authenticated-User": "alice"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "alice"
        assert data["auth_source"] == "frontdoor"
