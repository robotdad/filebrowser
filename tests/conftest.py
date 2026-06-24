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
    # SVG file (square, pixel dimensions)
    (tmp_path / "images" / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<circle cx="50" cy="50" r="40" fill="blue"/>'
        '</svg>'
    )
    # Tall SVG file (extreme aspect ratio, pt dimensions - regression test for viewer bug)
    (tmp_path / "images" / "tall.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100pt" height="175pt" viewBox="0 0 100 175">'
        '<rect x="10" y="10" width="80" height="155" fill="green"/>'
        '</svg>'
    )
    # Extension-less text files
    (tmp_path / "LICENSE").write_text("MIT License\n\nCopyright (c) 2024")
    (tmp_path / "Makefile").write_text("all:\n\techo hello")
    # Extension-less file that *looks* like text (content sniffing)
    (tmp_path / "mystery").write_text("just some plain text content")
    # Extension-less binary file
    (tmp_path / "binaryblob").write_bytes(b"\x00\x01\x02\xff\xfe binary data")
    # Minimal valid PDF
    (tmp_path / "sample.pdf").write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj "
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
        b"3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    # HTML files
    (tmp_path / "page.html").write_text(
        "<!DOCTYPE html><html><body><h1>Hello HTML</h1></body></html>"
    )
    (tmp_path / "malicious.html").write_text(
        '<html><body><script>alert(1)</script><img onerror="alert(2)" src=x></body></html>'
    )
    # .htm alias — must get the same html handling as .html
    (tmp_path / "page.htm").write_text(
        "<!DOCTYPE html><html><body><h1>Hello HTM</h1></body></html>"
    )
    return tmp_path


@pytest.fixture
def fs(tmp_home):
    """FilesystemService rooted at tmp_home."""
    return FilesystemService(tmp_home)


@pytest.fixture
def ext_dir(tmp_path):
    """An external directory outside the home dir."""
    ext = tmp_path / "external"
    ext.mkdir()
    (ext / "data.txt").write_text("external data")
    (ext / "subdir").mkdir()
    (ext / "subdir" / "nested.txt").write_text("nested content")
    return ext


@pytest.fixture
def fs_with_ext(tmp_home, ext_dir):
    """FilesystemService with an external location registered."""
    return FilesystemService(tmp_home, locations=[{"id": 1, "path": str(ext_dir)}])
