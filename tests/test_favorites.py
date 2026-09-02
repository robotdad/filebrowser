"""Tests for FavoritesService and the /api/favorites HTTP route."""

import concurrent.futures
import json
import os
import threading
import unittest.mock

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
    """TestClient exercising the real /api/favorites HTTP route.

    ``settings.home_dir`` is patched to ``tmp_path`` so that directories
    created under ``tmp_path`` pass the containment guard introduced by
    the path-validation layer.
    """
    import filebrowser.routes.favorites as fav_route

    app = FastAPI()
    app.include_router(favorites_router)
    app.dependency_overrides[get_favorites_service] = lambda: FavoritesService(
        tmp_path / "data"
    )
    app.dependency_overrides[require_auth] = lambda: "testuser"
    with unittest.mock.patch.object(
        fav_route.settings, "home_dir", tmp_path
    ), unittest.mock.patch.object(
        fav_route.settings, "data_dir", tmp_path / "data"
    ):
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


# ---------------------------------------------------------------------------
# NEW TESTS -- added to satisfy goal items 1-7
# ---------------------------------------------------------------------------


@pytest.fixture
def validated_client(tmp_path):
    """TestClient with settings.home_dir patched to tmp_path so that
    path-validation tests can exercise the containment guard without
    touching the real home directory."""
    import filebrowser.routes.favorites as fav_route

    app = FastAPI()
    app.include_router(favorites_router)
    app.dependency_overrides[get_favorites_service] = lambda: FavoritesService(
        tmp_path / "data"
    )
    app.dependency_overrides[require_auth] = lambda: "testuser"

    with unittest.mock.patch.object(
        fav_route.settings, "home_dir", tmp_path
    ), unittest.mock.patch.object(
        fav_route.settings, "data_dir", tmp_path / "data"
    ):
        with TestClient(app) as c:
            yield c, tmp_path


class TestDurableWritesFavorites:
    """Goal item 1: interrupted write must not corrupt the store."""

    def test_prior_favorites_survive_simulated_write_failure(self, svc, real_dir):
        """Simulate a failed save (e.g. disk full) during a second add.

        The first add must have committed its data durably; after the
        simulated failure the first entry must still be readable.
        """
        # Commit a first entry successfully.
        svc.add(str(real_dir))

        # Now simulate a write failure during the next save by patching
        # os.replace to raise OSError after the temp file is written.
        original_replace = os.replace

        call_count = {"n": 0}

        def fail_replace(src, dst):
            call_count["n"] += 1
            # Clean up the temp file to avoid leaving debris, then raise.
            try:
                os.unlink(src)
            except OSError:
                pass
            raise OSError("simulated disk failure")

        second_dir = real_dir.parent / "second"
        second_dir.mkdir()

        with unittest.mock.patch("os.replace", side_effect=fail_replace):
            with pytest.raises(OSError, match="simulated disk failure"):
                svc.add(str(second_dir))

        # The store must still be readable and must contain the first entry.
        reloaded = FavoritesService(svc._data_dir)
        favorites = reloaded.list()
        assert len(favorites) == 1, (
            f"Expected 1 favorite after failed write, got {favorites!r}"
        )
        assert favorites[0]["path"] == str(real_dir)

    def test_partial_temp_file_does_not_corrupt_store(self, svc, real_dir):
        """A leftover .tmp file in the data dir must not affect _load."""
        svc.add(str(real_dir))

        # Manually drop a partial/invalid temp file next to the store.
        tmp_debris = svc._data_dir / ".favorites_debris.tmp"
        tmp_debris.write_text("{ broken json", encoding="utf-8")

        # The store must still load cleanly.
        reloaded = FavoritesService(svc._data_dir)
        favorites = reloaded.list()
        assert len(favorites) == 1
        assert favorites[0]["path"] == str(real_dir)


class TestDurableWritesLocations:
    """Goal item 2: interrupted write must not corrupt the locations store."""

    def test_prior_locations_survive_simulated_write_failure(self, tmp_path):
        from filebrowser.services.locations import LocationsService

        data_dir = tmp_path / "ldata"
        svc = LocationsService(data_dir)
        d1 = tmp_path / "loc1"
        d1.mkdir()

        svc.add(str(d1))

        call_count = {"n": 0}

        def fail_replace(src, dst):
            call_count["n"] += 1
            try:
                os.unlink(src)
            except OSError:
                pass
            raise OSError("simulated disk failure")

        d2 = tmp_path / "loc2"
        d2.mkdir()

        with unittest.mock.patch("os.replace", side_effect=fail_replace):
            with pytest.raises(OSError, match="simulated disk failure"):
                svc.add(str(d2))

        reloaded = LocationsService(data_dir)
        locations = reloaded.list()
        assert len(locations) == 1, (
            f"Expected 1 location after failed write, got {locations!r}"
        )
        assert locations[0]["path"] == str(d1)


class TestConcurrentFavorites:
    """Goal item 3: concurrent add/remove must not lose updates."""

    def test_concurrent_adds_no_lost_updates(self, tmp_path):
        """Two threads each add a distinct directory; both must be stored."""
        data_dir = tmp_path / "data"
        dirs = []
        for i in range(10):
            d = tmp_path / f"dir{i}"
            d.mkdir()
            dirs.append(d)

        errors = []

        def add_all(worker_dirs):
            svc = FavoritesService(data_dir)
            for d in worker_dirs:
                try:
                    svc.add(str(d))
                except Exception as exc:
                    errors.append(exc)

        half = len(dirs) // 2
        t1 = threading.Thread(target=add_all, args=(dirs[:half],))
        t2 = threading.Thread(target=add_all, args=(dirs[half:],))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Concurrent add raised errors: {errors}"

        final = FavoritesService(data_dir).list()
        stored_paths = {f["path"] for f in final}
        for d in dirs:
            assert str(d) in stored_paths, (
                f"Lost update: {d} not in final store {stored_paths}"
            )

    def test_concurrent_add_and_remove_no_lost_updates(self, tmp_path):
        """One thread adds entries while another removes them; the final
        state must be consistent (no KeyError leaks, no phantom entries)."""
        data_dir = tmp_path / "data"
        svc = FavoritesService(data_dir)

        # Pre-populate entries that the remover will target.
        dirs_to_remove = []
        for i in range(5):
            d = tmp_path / f"remove_me_{i}"
            d.mkdir()
            svc.add(str(d))
            dirs_to_remove.append(d)

        dirs_to_add = []
        for i in range(5):
            d = tmp_path / f"add_me_{i}"
            d.mkdir()
            dirs_to_add.append(d)

        errors = []

        def adder():
            s = FavoritesService(data_dir)
            for d in dirs_to_add:
                try:
                    s.add(str(d))
                except Exception as exc:
                    errors.append(("add", exc))

        def remover():
            s = FavoritesService(data_dir)
            for d in dirs_to_remove:
                try:
                    s.remove(str(d))
                except KeyError:
                    pass  # already removed by another thread -- acceptable
                except Exception as exc:
                    errors.append(("remove", exc))

        t1 = threading.Thread(target=adder)
        t2 = threading.Thread(target=remover)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Concurrent add/remove raised errors: {errors}"

        final = FavoritesService(data_dir).list()
        stored_paths = {f["path"] for f in final}

        # Every successfully added entry must be present.
        for d in dirs_to_add:
            assert str(d) in stored_paths, (
                f"Lost add: {d} not in final store {stored_paths}"
            )

        # None of the removed entries should remain.
        for d in dirs_to_remove:
            assert str(d) not in stored_paths, (
                f"Phantom entry after remove: {d} still in {stored_paths}"
            )


class TestPathValidation:
    """Goal items 4, 5, 6, 7: POST /api/favorites path validation."""

    def test_empty_path_rejected_with_4xx(self, validated_client):
        client, tmp_path = validated_client
        response = client.post("/api/favorites", json={"path": ""})
        assert 400 <= response.status_code < 500, (
            f"Expected 4xx for empty path, got {response.status_code}: {response.text}"
        )
        # Must not be stored.
        assert client.get("/api/favorites").json() == []

    def test_empty_path_not_stored(self, validated_client):
        """Empty path must not resolve to CWD and be stored."""
        client, tmp_path = validated_client
        client.post("/api/favorites", json={"path": ""})
        favorites = client.get("/api/favorites").json()
        # CWD must not appear as a stored favorite.
        import os as _os
        cwd = str(_os.getcwd())
        stored_paths = [f["path"] for f in favorites]
        assert cwd not in stored_paths

    def test_nonexistent_path_rejected_with_4xx(self, validated_client):
        client, tmp_path = validated_client
        nonexistent = str(tmp_path / "does_not_exist")
        response = client.post("/api/favorites", json={"path": nonexistent})
        assert 400 <= response.status_code < 500, (
            f"Expected 4xx for nonexistent path, got {response.status_code}"
        )
        assert client.get("/api/favorites").json() == []

    def test_file_path_rejected_with_4xx(self, validated_client):
        client, tmp_path = validated_client
        f = tmp_path / "regular_file.txt"
        f.write_text("hello")
        response = client.post("/api/favorites", json={"path": str(f)})
        assert 400 <= response.status_code < 500, (
            f"Expected 4xx for file path, got {response.status_code}"
        )
        assert client.get("/api/favorites").json() == []

    def test_path_outside_home_rejected_with_4xx(self, validated_client):
        """An absolute path outside home_dir must be rejected."""
        client, tmp_path = validated_client
        # /tmp itself is outside tmp_path (the patched home_dir).
        import tempfile as _tempfile
        outside = _tempfile.gettempdir()
        response = client.post("/api/favorites", json={"path": outside})
        assert 400 <= response.status_code < 500, (
            f"Expected 4xx for path outside root, got {response.status_code}: {response.text}"
        )
        assert client.get("/api/favorites").json() == []

    def test_parent_relative_path_outside_root_rejected(self, validated_client):
        """A path that traverses above home_dir must be rejected."""
        client, tmp_path = validated_client
        # Create a subdir inside home so we can attempt to escape from it.
        sub = tmp_path / "sub"
        sub.mkdir()
        # Construct a path that escapes: sub/../.. goes above tmp_path.
        escaping = str(sub) + "/../../.."
        response = client.post("/api/favorites", json={"path": escaping})
        assert 400 <= response.status_code < 500, (
            f"Expected 4xx for escaping path, got {response.status_code}: {response.text}"
        )

    def test_rejections_are_never_500(self, validated_client):
        """All rejection cases must return client-error (4xx), never 500."""
        client, tmp_path = validated_client
        cases = [
            {"path": ""},
            {"path": str(tmp_path / "nonexistent")},
            {"path": "/tmp"},  # outside patched home_dir
        ]
        for body in cases:
            r = client.post("/api/favorites", json=body)
            assert r.status_code != 500, (
                f"Got 500 for body={body!r}: {r.text}"
            )
            assert r.status_code < 500, (
                f"Got server error {r.status_code} for body={body!r}: {r.text}"
            )

    def test_valid_path_inside_home_accepted(self, validated_client):
        """A real directory inside home_dir must be accepted."""
        client, tmp_path = validated_client
        inside = tmp_path / "valid_folder"
        inside.mkdir()
        response = client.post("/api/favorites", json={"path": str(inside)})
        assert response.status_code == 200, (
            f"Expected 200 for valid path, got {response.status_code}: {response.text}"
        )
