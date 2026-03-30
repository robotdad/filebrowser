"""Tests for LocationsService."""

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
