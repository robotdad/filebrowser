"""Tests for FavoritesService and the /api/favorites HTTP route."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from filebrowser.auth import require_auth
from filebrowser.routes.favorites import get_favorites_service
from filebrowser.routes.favorites import router as favorites_router
from filebrowser.services.favorites import FavoritesService


@pytest.fixture
def svc(tmp_path):
    """FavoritesService backed by a temporary data directory."""
    return FavoritesService(tmp_path / "data")


@pytest.fixture
def real_dir(tmp_path):
    """A real directory that can be pinned as a favorite."""
    d = tmp_path / "real_folder"
    d.mkdir()
    return d


class TestAddAndList:
    def test_add_and_list(self, svc, real_dir):
        entry = svc.add(str(real_dir))
        assert entry["path"] == str(real_dir)

        favorites = svc.list()
        assert len(favorites) == 1
        assert favorites[0]["path"] == str(real_dir)

    def test_add_multiple(self, svc, tmp_path):
        d1 = tmp_path / "dir1"
        d1.mkdir()
        d2 = tmp_path / "dir2"
        d2.mkdir()
        svc.add(str(d1))
        svc.add(str(d2))
        assert len(svc.list()) == 2

    def test_list_empty_returns_empty(self, svc):
        assert svc.list() == []

    def test_add_persists_across_new_instance(self, svc, real_dir, tmp_path):
        """A fresh FavoritesService instance against the same data_dir must
        see what an earlier instance wrote -- proof the store is on disk,
        not held only in the original Python object."""
        svc.add(str(real_dir))
        reloaded = FavoritesService(tmp_path / "data")
        favorites = reloaded.list()
        assert len(favorites) == 1
        assert favorites[0]["path"] == str(real_dir)

    def test_data_dir_scoping(self, tmp_path, real_dir):
        """Two services backed by different data_dirs must not share state."""
        svc_a = FavoritesService(tmp_path / "data_a")
        svc_b = FavoritesService(tmp_path / "data_b")
        svc_a.add(str(real_dir))
        assert svc_a.list() != []
        assert svc_b.list() == []


class TestIdempotentAdd:
    """AC-3: idempotent add via resolved/canonicalized path equality --
    diverges deliberately from LocationsService.add, which raises on a
    duplicate. Favorites must not raise on a repeated add."""

    def test_add_duplicate_does_not_raise(self, svc, real_dir):
        svc.add(str(real_dir))
        svc.add(str(real_dir))  # must not raise
        assert len(svc.list()) == 1

    def test_add_duplicate_returns_existing_entry(self, svc, real_dir):
        first = svc.add(str(real_dir))
        second = svc.add(str(real_dir))
        assert first == second

    def test_dedupe_via_resolved_path_equality(self, svc, tmp_path):
        """Differently-spelled paths that resolve to the same real
        directory collapse to a single entry (Path(...).resolve() rule,
        matching LocationsService's own oracle)."""
        real = tmp_path / "target"
        real.mkdir()

        svc.add(str(real))
        svc.add(str(tmp_path / "target" / "."))
        svc.add(str(tmp_path) + "/./target")

        favorites = svc.list()
        assert len(favorites) == 1

    def test_dedupe_does_not_over_fire(self, svc, tmp_path):
        d1 = tmp_path / "dir1"
        d1.mkdir()
        d2 = tmp_path / "dir2"
        d2.mkdir()
        svc.add(str(d1))
        svc.add(str(d2))
        assert len(svc.list()) == 2


class TestRemove:
    """AC-2: removal is identified by path value, never a numeric id."""

    def test_remove_by_path(self, svc, real_dir):
        svc.add(str(real_dir))
        svc.remove(str(real_dir))
        assert svc.list() == []

    def test_remove_nonexistent_raises(self, svc, tmp_path):
        with pytest.raises(KeyError):
            svc.remove(str(tmp_path / "never_added"))

    def test_remove_only_target(self, svc, tmp_path):
        d1 = tmp_path / "dir1"
        d1.mkdir()
        d2 = tmp_path / "dir2"
        d2.mkdir()
        svc.add(str(d1))
        svc.add(str(d2))
        svc.remove(str(d1))
        remaining = svc.list()
        assert len(remaining) == 1
        assert remaining[0]["path"] == str(d2)

    def test_remove_by_unresolved_spelling(self, svc, tmp_path):
        """Remove must match by resolved path, so a differently-spelled
        (but resolved-equal) path value also identifies the entry."""
        real = tmp_path / "target"
        real.mkdir()
        svc.add(str(real))
        svc.remove(str(tmp_path / "target" / "."))
        assert svc.list() == []

    def test_remove_persists_across_new_instance(self, svc, real_dir, tmp_path):
        svc.add(str(real_dir))
        svc.remove(str(real_dir))
        reloaded = FavoritesService(tmp_path / "data")
        assert reloaded.list() == []


@pytest.fixture
def client(tmp_path):
    """TestClient exercising the real /api/favorites HTTP route."""
    app = FastAPI()
    app.include_router(favorites_router)
    app.dependency_overrides[get_favorites_service] = lambda: FavoritesService(
        tmp_path / "data"
    )
    app.dependency_overrides[require_auth] = lambda: "testuser"
    with TestClient(app) as c:
        yield c


class TestHttpRoute:
    """Exercises the actual FastAPI/ASGI surface, not just the service
    class, per the criteria's "through the backend API" language."""

    def test_add_via_post_body(self, client, real_dir):
        response = client.post("/api/favorites", json={"path": str(real_dir)})
        assert response.status_code == 200
        assert response.json()["path"] == str(real_dir)

    def test_list_via_get(self, client, real_dir):
        client.post("/api/favorites", json={"path": str(real_dir)})
        response = client.get("/api/favorites")
        assert response.status_code == 200
        paths = [f["path"] for f in response.json()]
        assert str(real_dir) in paths

    def test_remove_via_query_string(self, client, real_dir):
        client.post("/api/favorites", json={"path": str(real_dir)})
        response = client.request(
            "DELETE", "/api/favorites", params={"path": str(real_dir)}
        )
        assert response.status_code == 200
        assert client.get("/api/favorites").json() == []

    def test_remove_via_json_body(self, client, real_dir):
        client.post("/api/favorites", json={"path": str(real_dir)})
        response = client.request(
            "DELETE", "/api/favorites", json={"path": str(real_dir)}
        )
        assert response.status_code == 200
        assert client.get("/api/favorites").json() == []

    def test_remove_identifies_by_path_not_id(self, client, tmp_path):
        """Two favorites are added; removing one BY PATH must leave the
        other untouched, regardless of add order -- proving identification
        is genuinely path-based, not positional/id-based."""
        d1 = tmp_path / "dir1"
        d1.mkdir()
        d2 = tmp_path / "dir2"
        d2.mkdir()
        client.post("/api/favorites", json={"path": str(d1)})
        client.post("/api/favorites", json={"path": str(d2)})

        response = client.request("DELETE", "/api/favorites", params={"path": str(d2)})
        assert response.status_code == 200

        paths = [f["path"] for f in client.get("/api/favorites").json()]
        assert str(d1) in paths
        assert str(d2) not in paths

    def test_add_duplicate_via_http_does_not_error(self, client, real_dir):
        first = client.post("/api/favorites", json={"path": str(real_dir)})
        second = client.post("/api/favorites", json={"path": str(real_dir)})
        assert first.status_code == 200
        assert second.status_code == 200
        assert len(client.get("/api/favorites").json()) == 1

    def test_remove_missing_path_value_is_rejected(self, client):
        response = client.request("DELETE", "/api/favorites")
        assert response.status_code == 400
