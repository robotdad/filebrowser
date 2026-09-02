"""Tests for LocationsService."""

import os
import unittest.mock

import pytest

from filebrowser.services.locations import LocationsService


@pytest.fixture
def svc(tmp_path):
    """LocationsService backed by a temporary data directory."""
    return LocationsService(tmp_path / "data")


@pytest.fixture
def real_dir(tmp_path):
    """A real directory that can be registered as an external location."""
    d = tmp_path / "real_folder"
    d.mkdir()
    return d


class TestAddAndList:
    def test_add_and_list(self, svc, real_dir):
        entry = svc.add(str(real_dir))
        assert entry["id"] == 1
        assert entry["path"] == str(real_dir)
        assert entry["name"] == real_dir.name

        locations = svc.list()
        assert len(locations) == 1
        assert locations[0]["id"] == 1

    def test_add_with_custom_name(self, svc, real_dir):
        entry = svc.add(str(real_dir), name="My Folder")
        assert entry["name"] == "My Folder"

    def test_add_multiple(self, svc, tmp_path):
        d1 = tmp_path / "dir1"
        d1.mkdir()
        d2 = tmp_path / "dir2"
        d2.mkdir()
        e1 = svc.add(str(d1))
        e2 = svc.add(str(d2))
        assert e1["id"] == 1
        assert e2["id"] == 2
        assert len(svc.list()) == 2

    def test_list_empty_returns_empty(self, svc):
        assert svc.list() == []


class TestAddValidation:
    def test_add_nonexistent_path_raises(self, svc, tmp_path):
        with pytest.raises(FileNotFoundError):
            svc.add(str(tmp_path / "does_not_exist"))

    def test_add_file_instead_of_dir_raises(self, svc, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello")
        with pytest.raises(NotADirectoryError):
            svc.add(str(f))

    def test_add_duplicate_raises(self, svc, real_dir):
        svc.add(str(real_dir))
        with pytest.raises(ValueError, match="already registered"):
            svc.add(str(real_dir))


class TestRemove:
    def test_remove(self, svc, real_dir):
        svc.add(str(real_dir))
        svc.remove(1)
        assert svc.list() == []

    def test_remove_nonexistent_raises(self, svc):
        with pytest.raises(KeyError):
            svc.remove(999)

    def test_remove_only_target(self, svc, tmp_path):
        d1 = tmp_path / "dir1"
        d1.mkdir()
        d2 = tmp_path / "dir2"
        d2.mkdir()
        svc.add(str(d1))
        svc.add(str(d2))
        svc.remove(1)
        remaining = svc.list()
        assert len(remaining) == 1
        assert remaining[0]["id"] == 2


class TestGet:
    def test_get_existing(self, svc, real_dir):
        svc.add(str(real_dir))
        loc = svc.get(1)
        assert loc is not None
        assert loc["id"] == 1

    def test_get_nonexistent_returns_none(self, svc):
        assert svc.get(999) is None


class TestIdsAreStable:
    def test_ids_increment_dont_reuse(self, svc, tmp_path):
        """After add, remove, add the new ID should be 2, not reusing 1."""
        d1 = tmp_path / "dir1"
        d1.mkdir()
        d2 = tmp_path / "dir2"
        d2.mkdir()

        e1 = svc.add(str(d1))
        assert e1["id"] == 1

        svc.remove(1)

        e2 = svc.add(str(d2))
        assert e2["id"] == 2  # IDs never reuse

    def test_ids_are_unique_across_adds(self, svc, tmp_path):
        dirs = []
        for i in range(5):
            d = tmp_path / f"dir{i}"
            d.mkdir()
            dirs.append(d)

        entries = [svc.add(str(d)) for d in dirs]
        ids = [e["id"] for e in entries]
        assert ids == list(range(1, 6))
        assert len(set(ids)) == 5  # all unique


# ---------------------------------------------------------------------------
# NEW TESTS -- added to satisfy goal item 2 (durable writes in LocationsService)
# ---------------------------------------------------------------------------


class TestDurableWritesLocations:
    """Goal item 2: interrupted write must not corrupt the locations store."""

    def test_prior_locations_survive_simulated_write_failure(self, tmp_path):
        """Simulate a failed save during a second add.

        The first add must have committed its data durably; after the
        simulated failure the first entry must still be readable.
        """
        data_dir = tmp_path / "data"
        svc = LocationsService(data_dir)
        d1 = tmp_path / "loc1"
        d1.mkdir()

        # First add succeeds.
        svc.add(str(d1))

        def fail_replace(src, dst):
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

        # The store must still be readable and contain only the first entry.
        reloaded = LocationsService(data_dir)
        locations = reloaded.list()
        assert len(locations) == 1, (
            f"Expected 1 location after failed write, got {locations!r}"
        )
        assert locations[0]["path"] == str(d1)

    def test_partial_temp_file_does_not_corrupt_store(self, svc, real_dir):
        """A leftover .tmp file in the data dir must not affect _load."""
        svc.add(str(real_dir))

        # Manually drop a partial/invalid temp file next to the store.
        tmp_debris = svc._data_dir / ".locations_debris.tmp"
        tmp_debris.write_text("{ broken json", encoding="utf-8")

        # The store must still load cleanly.
        reloaded = LocationsService(svc._data_dir)
        locations = reloaded.list()
        assert len(locations) == 1
        assert locations[0]["path"] == str(real_dir)
