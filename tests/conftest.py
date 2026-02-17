import pytest
from filebrowser.services.filesystem import FilesystemService


@pytest.fixture
def tmp_home(tmp_path):
    """Create a temporary home directory with test files."""
    # Directories
    (tmp_path / "docs").mkdir()
    (tmp_path / "images").mkdir()
    (tmp_path / "empty_dir").mkdir()
    # Text files
    (tmp_path / "hello.txt").write_text("Hello World")
    (tmp_path / "docs" / "readme.md").write_text("# Title\n\nSome content.")
    (tmp_path / "docs" / "notes.txt").write_text("Line 1\nLine 2\nLine 3")
    (tmp_path / "data.csv").write_text("a,b,c\n1,2,3")
    # Code files
    (tmp_path / "script.py").write_text("print('hello')")
    # Binary files
    (tmp_path / "images" / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0fake-jpg")
    return tmp_path


@pytest.fixture
def fs(tmp_home):
    """FilesystemService rooted at tmp_home."""
    return FilesystemService(tmp_home)
