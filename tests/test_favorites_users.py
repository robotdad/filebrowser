"""Authenticated per-user favorites persistence tests."""

import hashlib
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from filebrowser.auth import create_session_token
from filebrowser.routes.favorites import router as favorites_router
from filebrowser.services.favorites import FavoritesService


@pytest.fixture
def authenticated_clients(tmp_path, monkeypatch):
    """Independent cookie-authenticated clients using the real service dependency."""
    import filebrowser.auth as auth_module
    import filebrowser.routes.favorites as favorites_route

    home_dir = tmp_path / "home"
    data_dir = tmp_path / "data"
    home_dir.mkdir()
    monkeypatch.setattr(favorites_route.settings, "home_dir", home_dir)
    monkeypatch.setattr(favorites_route.settings, "data_dir", data_dir)
    monkeypatch.setattr(auth_module.settings, "secret_key", "favorites-test-secret")
    monkeypatch.setattr(auth_module.settings, "session_timeout", 3600)

    app = FastAPI()
    app.include_router(favorites_router)

    with TestClient(app) as alice, TestClient(app) as bob:
        alice.cookies.set(
            "session", create_session_token("alice", auth_module.settings.secret_key)
        )
        bob.cookies.set(
            "session", create_session_token("bob", auth_module.settings.secret_key)
        )
        yield alice, bob, data_dir, home_dir


def _user_store(data_dir, username):
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return data_dir / "favorites-users" / f"{digest}.json"


class TestAuthenticatedUserFavorites:
    def test_cookie_users_have_independent_favorites_and_persist(
        self, authenticated_clients
    ):
        alice, bob, data_dir, home_dir = authenticated_clients
        shared = home_dir / "shared"
        shared.mkdir()

        first = alice.post("/api/favorites", json={"path": str(shared)})
        duplicate = alice.post("/api/favorites", json={"path": str(shared)})
        assert first.status_code == 200
        assert duplicate.status_code == 200
        assert duplicate.json() == first.json()
        assert alice.get("/api/favorites").json() == [{"path": str(shared)}]

        assert bob.get("/api/favorites").json() == []
        missing = bob.delete("/api/favorites", params={"path": str(shared)})
        assert missing.status_code == 404
        assert alice.get("/api/favorites").json() == [{"path": str(shared)}]

        assert bob.post("/api/favorites", json={"path": str(shared)}).status_code == 200
        assert bob.delete("/api/favorites", params={"path": str(shared)}).status_code == 200
        assert bob.get("/api/favorites").json() == []
        assert alice.get("/api/favorites").json() == [{"path": str(shared)}]

        assert FavoritesService(data_dir, "alice").list() == [{"path": str(shared)}]
        assert FavoritesService(data_dir, "bob").list() == []
        assert _user_store(data_dir, "alice") != _user_store(data_dir, "bob")
        assert _user_store(data_dir, "alice").is_file()
        assert _user_store(data_dir, "bob").is_file()

    def test_authenticated_requests_do_not_touch_corrupt_legacy_store(
        self, authenticated_clients
    ):
        alice, _, data_dir, home_dir = authenticated_clients
        data_dir.mkdir()
        legacy_store = data_dir / "favorites.json"
        legacy_bytes = b"{ corrupt legacy favorites: do not rewrite }\n"
        legacy_store.write_bytes(legacy_bytes)
        favorite = home_dir / "favorite"
        favorite.mkdir()

        assert alice.get("/api/favorites").json() == []
        assert alice.post("/api/favorites", json={"path": str(favorite)}).status_code == 200

        assert legacy_store.read_bytes() == legacy_bytes
        assert FavoritesService(data_dir, "alice").list() == [{"path": str(favorite)}]

    def test_unauthenticated_favorites_endpoints_are_denied(
        self, authenticated_clients
    ):
        _, _, _, home_dir = authenticated_clients
        favorite = home_dir / "favorite"
        favorite.mkdir()
        app = FastAPI()
        app.include_router(favorites_router)

        with TestClient(app) as client:
            assert client.get("/api/favorites").status_code == 401
            assert client.post(
                "/api/favorites", json={"path": str(favorite)}
            ).status_code == 401
            assert client.delete(
                "/api/favorites", params={"path": str(favorite)}
            ).status_code == 401

    def test_header_identity_uses_the_exact_username_store(
        self, authenticated_clients
    ):
        _, _, data_dir, home_dir = authenticated_clients
        favorite = home_dir / "header-favorite"
        favorite.mkdir()
        username = "Header User"

        app = FastAPI()
        app.include_router(favorites_router)
        with TestClient(app) as client:
            response = client.post(
                "/api/favorites",
                headers={"X-Authenticated-User": username},
                json={"path": str(favorite)},
            )

        assert response.status_code == 200
        assert FavoritesService(data_dir, username).list() == [{"path": str(favorite)}]
        assert FavoritesService(data_dir, username.lower()).list() == []


class TestUserStoreSafety:
    def test_explicit_empty_username_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="Username must not be empty"):
            FavoritesService(tmp_path / "data", "")

    def test_malicious_username_cannot_traverse_store_path(
        self, authenticated_clients
    ):
        _, _, data_dir, home_dir = authenticated_clients
        username = "../../outside\\user"
        favorite = home_dir / "favorite"
        favorite.mkdir()
        app = FastAPI()
        app.include_router(favorites_router)

        with TestClient(app) as client:
            client.cookies.set(
                "session", create_session_token(username, "favorites-test-secret")
            )
            response = client.post("/api/favorites", json={"path": str(favorite)})

        expected_store = _user_store(data_dir, username)
        assert response.status_code == 200
        assert expected_store.is_file()
        assert expected_store.parent == data_dir / "favorites-users"
        assert not (data_dir.parent / "outside").exists()
        assert not (data_dir / "favorites.json").exists()

    def test_same_user_concurrency_and_other_user_isolation(self, tmp_path):
        data_dir = tmp_path / "data"
        directories = []
        for number in range(12):
            directory = tmp_path / f"favorite-{number}"
            directory.mkdir()
            directories.append(directory)

        errors = []

        def add_favorite(directory):
            try:
                FavoritesService(data_dir, "alice").add(str(directory))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=add_favorite, args=(directory,)) for directory in directories]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert {entry["path"] for entry in FavoritesService(data_dir, "alice").list()} == {
            str(directory) for directory in directories
        }

        FavoritesService(data_dir, "bob").add(str(directories[0]))
        assert FavoritesService(data_dir, "bob").list() == [
            {"path": str(directories[0])}
        ]
        assert len(FavoritesService(data_dir, "alice").list()) == len(directories)