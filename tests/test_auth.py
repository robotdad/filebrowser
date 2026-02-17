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
        request.cookies = {}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert exc_info.value.status_code == 401

    def test_invalid_cookie_raises_401(self):
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.cookies = {"session": "garbage-token"}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert exc_info.value.status_code == 401


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
        assert response.json() == {"username": "testuser"}
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
        assert response.json() == {"ok": True}


class TestMeRoute:
    def test_me_with_valid_session(self, auth_client):
        with patch("filebrowser.routes.auth.authenticate_pam", return_value=True):
            auth_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "testpass"},
            )
        response = auth_client.get("/api/auth/me")
        assert response.status_code == 200
        assert response.json() == {"username": "testuser"}

    def test_me_without_session(self, auth_client):
        response = auth_client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_with_invalid_session(self, auth_client):
        auth_client.cookies.set("session", "invalid-token")
        response = auth_client.get("/api/auth/me")
        assert response.status_code == 401
