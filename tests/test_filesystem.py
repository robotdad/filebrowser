import tempfile
from pathlib import Path

import pytest


class TestValidatePath:
    def test_valid_relative_path(self, fs, tmp_home):
        result = fs.validate_path("hello.txt")
        assert result == tmp_home / "hello.txt"

    def test_valid_nested_path(self, fs, tmp_home):
        result = fs.validate_path("docs/readme.md")
        assert result == tmp_home / "docs" / "readme.md"

    def test_empty_path_returns_home(self, fs, tmp_home):
        result = fs.validate_path("")
        assert result == tmp_home

    def test_root_slash_returns_home(self, fs, tmp_home):
        result = fs.validate_path("/")
        assert result == tmp_home

    def test_rejects_dotdot_traversal(self, fs):
        with pytest.raises(PermissionError):
            fs.validate_path("../../etc/passwd")

    def test_rejects_dotdot_in_middle(self, fs):
        with pytest.raises(PermissionError):
            fs.validate_path("docs/../../etc/passwd")

    def test_absolute_path_stays_within_home(self, fs, tmp_home):
        result = fs.validate_path("/hello.txt")
        assert result == tmp_home / "hello.txt"


class TestListDirectory:
    def test_list_root(self, fs):
        entries = fs.list_directory("")
        names = [e["name"] for e in entries]
        assert "docs" in names
        assert "hello.txt" in names

    def test_entries_have_required_fields(self, fs):
        entries = fs.list_directory("")
        for entry in entries:
            assert "name" in entry
            assert "type" in entry
            assert "size" in entry
            assert "modified" in entry

    def test_directories_listed_before_files(self, fs):
        entries = fs.list_directory("")
        types = [e["type"] for e in entries]
        dir_done = False
        for t in types:
            if t == "file":
                dir_done = True
            if t == "directory" and dir_done:
                pytest.fail("Directory appeared after a file in listing")

    def test_list_subdirectory(self, fs):
        entries = fs.list_directory("docs")
        names = [e["name"] for e in entries]
        assert "readme.md" in names
        assert "notes.txt" in names

    def test_list_empty_directory(self, fs):
        entries = fs.list_directory("empty_dir")
        assert entries == []

    def test_list_nonexistent_directory_raises(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.list_directory("nonexistent")

    def test_list_file_raises(self, fs):
        with pytest.raises(NotADirectoryError):
            fs.list_directory("hello.txt")


class TestDetectFileType:
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("readme.md", "markdown"),
            ("script.py", "code"),
            ("app.js", "code"),
            ("styles.css", "code"),
            ("notes.txt", "text"),
            ("data.json", "text"),
            ("config.yaml", "text"),
            ("server.log", "text"),
            ("photo.jpg", "image"),
            ("photo.jpeg", "image"),
            ("icon.png", "image"),
            ("banner.svg", "image"),
            ("song.mp3", "audio"),
            ("track.flac", "audio"),
            ("clip.mp4", "video"),
            ("movie.mkv", "video"),
            ("document.pdf", "pdf"),
            ("archive.zip", "other"),
            ("noext", "other"),
        ],
    )
    def test_detects_category(self, fs, filename, expected):
        assert fs.detect_file_type(filename) == expected

    def test_case_insensitive(self, fs):
        assert fs.detect_file_type("PHOTO.JPG") == "image"
        assert fs.detect_file_type("Script.PY") == "code"


class TestGetInfo:
    def test_file_info(self, fs):
        info = fs.get_info("hello.txt")
        assert info["name"] == "hello.txt"
        assert info["type"] == "file"
        assert info["size"] == len("Hello World")
        assert info["category"] == "text"
        assert "modified" in info

    def test_directory_info(self, fs):
        info = fs.get_info("docs")
        assert info["name"] == "docs"
        assert info["type"] == "directory"
        assert info["category"] is None

    def test_info_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.get_info("nonexistent.txt")


class TestGetFilePath:
    def test_returns_path_for_existing_file(self, fs, tmp_home):
        result = fs.get_file_path("hello.txt")
        assert result == tmp_home / "hello.txt"

    def test_raises_for_nonexistent(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.get_file_path("nonexistent.txt")

    def test_raises_for_directory(self, fs):
        with pytest.raises(IsADirectoryError):
            fs.get_file_path("docs")


class TestReadFile:
    def test_read_text_file(self, fs):
        content = fs.read_file("hello.txt")
        assert content == "Hello World"

    def test_read_nested_file(self, fs):
        content = fs.read_file("docs/readme.md")
        assert content.startswith("# Title")

    def test_read_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.read_file("nonexistent.txt")


class TestDelete:
    def test_delete_file(self, fs, tmp_home):
        target = tmp_home / "to_delete.txt"
        target.write_text("delete me")
        fs.delete("to_delete.txt")
        assert not target.exists()

    def test_delete_directory(self, fs, tmp_home):
        target = tmp_home / "to_delete_dir"
        target.mkdir()
        (target / "child.txt").write_text("child")
        fs.delete("to_delete_dir")
        assert not target.exists()

    def test_delete_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.delete("nonexistent")


class TestMkdir:
    def test_create_directory(self, fs, tmp_home):
        fs.mkdir("new_folder")
        assert (tmp_home / "new_folder").is_dir()

    def test_create_nested_directory(self, fs, tmp_home):
        fs.mkdir("new_parent/new_child")
        assert (tmp_home / "new_parent" / "new_child").is_dir()

    def test_existing_directory_is_ok(self, fs, tmp_home):
        fs.mkdir("docs")
        assert (tmp_home / "docs").is_dir()


class TestRename:
    def test_rename_file(self, fs, tmp_home):
        fs.rename("hello.txt", "goodbye.txt")
        assert not (tmp_home / "hello.txt").exists()
        assert (tmp_home / "goodbye.txt").exists()
        assert (tmp_home / "goodbye.txt").read_text() == "Hello World"

    def test_move_file_to_subdirectory(self, fs, tmp_home):
        fs.rename("hello.txt", "docs/hello.txt")
        assert not (tmp_home / "hello.txt").exists()
        assert (tmp_home / "docs" / "hello.txt").exists()

    def test_rename_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError):
            fs.rename("nonexistent.txt", "other.txt")


class TestSecurityPathTraversal:
    def test_dotdot_etc_passwd(self, fs):
        with pytest.raises(PermissionError):
            fs.validate_path("../../etc/passwd")

    def test_double_encoded_dotdot(self, fs):
        with pytest.raises(PermissionError):
            fs.validate_path("..%2F..%2Fetc%2Fpasswd/../../../etc/passwd")

    def test_symlink_outside_home(self, fs, tmp_home):
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, "secret.txt").write_text("secret data")
            link = tmp_home / "evil_link"
            link.symlink_to(outside)
            with pytest.raises(PermissionError):
                fs.validate_path("evil_link/secret.txt")

    def test_symlink_file_outside_home(self, fs, tmp_home):
        with tempfile.TemporaryDirectory() as outside:
            secret = Path(outside) / "secret.txt"
            secret.write_text("secret")
            (tmp_home / "link_to_secret").symlink_to(secret)
            with pytest.raises(PermissionError):
                fs.validate_path("link_to_secret")

    def test_deeply_nested_traversal(self, fs):
        with pytest.raises(PermissionError):
            fs.validate_path("a/b/c/../../../../etc/passwd")

    def test_delete_rejects_traversal(self, fs):
        with pytest.raises(PermissionError):
            fs.delete("../../etc/important")

    def test_rename_rejects_traversal_in_source(self, fs):
        with pytest.raises(PermissionError):
            fs.rename("../../etc/passwd", "stolen.txt")

    def test_rename_rejects_traversal_in_dest(self, fs, tmp_home):
        with pytest.raises(PermissionError):
            fs.rename("hello.txt", "../../tmp/stolen.txt")

    def test_mkdir_rejects_traversal(self, fs):
        with pytest.raises(PermissionError):
            fs.mkdir("../../tmp/evil_dir")

    def test_cannot_delete_home_directory(self, fs):
        with pytest.raises(PermissionError):
            fs.delete("")
