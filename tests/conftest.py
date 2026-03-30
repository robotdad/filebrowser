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
    # Hidden files/dirs
    (tmp_path / ".hidden_file").write_text("secret")
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "settings.json").write_text("{}")
    # Binary files
    (tmp_path / "images" / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0fake-jpg")
    # Extension-less text files
    (tmp_path / "LICENSE").write_text("MIT License\n\nCopyright (c) 2024")
    (tmp_path / "Makefile").write_text("all:\n\techo hello")
    # Extension-less file that *looks* like text (content sniffing)
    (tmp_path / "mystery").write_text("just some plain text content")
    # Extension-less binary file
    (tmp_path / "binaryblob").write_bytes(b"\x00\x01\x02\xff\xfe binary data")
    return tmp_path


@pytest.fixture
def fs(tmp_home):
    """FilesystemService rooted at tmp_home."""
    return FilesystemService(tmp_home)
