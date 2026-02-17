# Filebrowser Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Build a web-based remote file browser for headless Linux machines, accessible over Tailscale.

**Architecture:** FastAPI backend serves a REST API and static frontend assets. Preact + HTM frontend (no build step) provides a two-panel file browser with lazy-loaded file tree and type-aware preview. Caddy reverse proxy terminates HTTPS using Tailscale-generated certificates. PAM authentication with signed session cookies. All file operations scoped to the user's home directory.

**Tech Stack:** Python 3.11+ (FastAPI, uvicorn, itsdangerous, python-pam), Preact + HTM (CDN, ES modules), highlight.js, marked.js, Caddy, systemd

---

## Phase 1: Scaffolding + Core Services

### Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `filebrowser/__init__.py`
- Create: `filebrowser/routes/__init__.py`
- Create: `filebrowser/services/__init__.py`
- Create: `filebrowser/static/.gitkeep`
- Create: `filebrowser/static/css/.gitkeep`
- Create: `filebrowser/static/js/.gitkeep`
- Create: `filebrowser/static/js/components/.gitkeep`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "filebrowser"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "python-pam",
    "python-multipart",
    "itsdangerous",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "httpx",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 2: Create directory structure and all `__init__.py` files**

```bash
cd /Users/robotdad/Source/filebrowser
mkdir -p filebrowser/routes filebrowser/services filebrowser/static/css filebrowser/static/js/components tests deploy
touch filebrowser/__init__.py filebrowser/routes/__init__.py filebrowser/services/__init__.py tests/__init__.py
```

Every `__init__.py` is empty. They just mark directories as Python packages.

**Step 3: Create `tests/conftest.py` with shared fixtures**

```python
import pytest
from pathlib import Path
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
```

**Step 4: Create venv and install dependencies**

```bash
cd /Users/robotdad/Source/filebrowser
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Note: `pip install -e ".[dev]"` will fail until we create the `filebrowser/config.py` and `filebrowser/services/filesystem.py` modules (referenced in conftest). That's expected — we just need the venv and packages installed. Create placeholder files to unblock:

```bash
touch filebrowser/config.py filebrowser/services/filesystem.py filebrowser/auth.py
touch filebrowser/routes/auth.py filebrowser/routes/files.py filebrowser/main.py
```

Now re-run install:

```bash
pip install -e ".[dev]"
```

**Step 5: Verify pytest runs (with no tests yet)**

```bash
cd /Users/robotdad/Source/filebrowser
python -m pytest tests/ -v
```

Expected: `no tests ran` with exit code 5 (no tests collected). This confirms the test infrastructure works.

**Step 6: Initialize git and commit**

```bash
cd /Users/robotdad/Source/filebrowser
git init
echo -e ".venv/\n__pycache__/\n*.egg-info/\n*.pyc\ndist/\nbuild/\n.eggs/" > .gitignore
git add -A
git commit -m "chore: project scaffolding with pyproject.toml and directory structure"
```

---

### Task 2: Config Module

**Files:**
- Create: `filebrowser/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from pathlib import Path


def test_settings_has_correct_defaults():
    from filebrowser.config import Settings

    s = Settings()
    assert s.home_dir == Path.home()
    assert s.session_timeout == 86400
    assert s.upload_max_size == 1_073_741_824
    assert isinstance(s.secret_key, str)
    assert len(s.secret_key) >= 32


def test_settings_accepts_custom_values(tmp_path):
    from filebrowser.config import Settings

    s = Settings(
        home_dir=tmp_path,
        session_timeout=3600,
        upload_max_size=500,
        secret_key="my-test-secret",
    )
    assert s.home_dir == tmp_path
    assert s.session_timeout == 3600
    assert s.upload_max_size == 500
    assert s.secret_key == "my-test-secret"


def test_settings_reads_secret_from_env(monkeypatch):
    from filebrowser.config import Settings

    monkeypatch.setenv("FILEBROWSER_SECRET_KEY", "env-secret-value")
    s = Settings()
    assert s.secret_key == "env-secret-value"
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/robotdad/Source/filebrowser
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `Settings` class doesn't exist yet (the file is empty).

**Step 3: Implement the config module**

Write `filebrowser/config.py`:

```python
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    home_dir: Path = field(default_factory=Path.home)
    session_timeout: int = 86400  # 24 hours in seconds
    upload_max_size: int = 1_073_741_824  # 1 GB in bytes
    secret_key: str = field(
        default_factory=lambda: os.environ.get(
            "FILEBROWSER_SECRET_KEY", secrets.token_hex(32)
        )
    )


settings = Settings()
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 3 passed.

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: config module with Settings dataclass"
```

---

### Task 3: Filesystem Service — Path Validation, Directory Listing, File Type Detection

This task builds the `FilesystemService` class using TDD. Each sub-task writes the test first, then implements the method.

**Files:**
- Create: `filebrowser/services/filesystem.py`
- Create: `tests/test_filesystem.py`

#### Task 3a: Path Validation

**Step 1: Write the failing tests**

Create `tests/test_filesystem.py`:

```python
import pytest
from pathlib import Path
from filebrowser.services.filesystem import FilesystemService


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
        """Absolute paths get stripped of leading slash and treated as relative."""
        result = fs.validate_path("/hello.txt")
        assert result == tmp_home / "hello.txt"
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_filesystem.py::TestValidatePath -v
```

Expected: FAIL — `FilesystemService` has no `validate_path` method.

**Step 3: Implement path validation**

Write `filebrowser/services/filesystem.py`:

```python
from pathlib import Path
from datetime import datetime

FILE_CATEGORIES = {
    "text": {".txt", ".log", ".csv", ".json", ".xml", ".yaml", ".yml", ".toml", ".env", ".conf"},
    "code": {".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp", ".java", ".sh", ".sql", ".html", ".css"},
    "markdown": {".md"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"},
    "audio": {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"},
    "video": {".mp4", ".webm", ".mkv", ".mov", ".avi"},
    "pdf": {".pdf"},
}


class FilesystemService:
    def __init__(self, home_dir: Path):
        self.home_dir = home_dir.resolve()

    def validate_path(self, path: str) -> Path:
        """Resolve path and verify it stays within home_dir."""
        cleaned = path.lstrip("/")
        resolved = (self.home_dir / cleaned).resolve()
        try:
            resolved.relative_to(self.home_dir)
        except ValueError:
            raise PermissionError(f"Path outside home directory: {path}")
        return resolved
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_filesystem.py::TestValidatePath -v
```

Expected: 7 passed.

#### Task 3b: Directory Listing

**Step 1: Write the failing tests**

Append to `tests/test_filesystem.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_filesystem.py::TestListDirectory -v
```

Expected: FAIL — `list_directory` doesn't exist.

**Step 3: Implement directory listing**

Add to the `FilesystemService` class in `filebrowser/services/filesystem.py`:

```python
    def list_directory(self, path: str = "") -> list[dict]:
        """List directory contents. Directories first, then files, alphabetical."""
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        entries = []
        for entry in sorted(resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return entries
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_filesystem.py::TestListDirectory -v
```

Expected: 7 passed.

#### Task 3c: File Type Detection and File Info

**Step 1: Write the failing tests**

Append to `tests/test_filesystem.py`:

```python
class TestDetectFileType:
    @pytest.mark.parametrize("filename,expected", [
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
    ])
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
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_filesystem.py::TestDetectFileType tests/test_filesystem.py::TestGetInfo -v
```

Expected: FAIL — methods don't exist.

**Step 3: Implement file type detection and info**

Add to the `FilesystemService` class in `filebrowser/services/filesystem.py`:

```python
    def detect_file_type(self, filename: str) -> str:
        """Detect file type category by extension."""
        ext = Path(filename).suffix.lower()
        for category, extensions in FILE_CATEGORIES.items():
            if ext in extensions:
                return category
        return "other"

    def get_info(self, path: str) -> dict:
        """Get metadata for a single file or directory."""
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        stat = resolved.stat()
        return {
            "name": resolved.name,
            "path": str(resolved.relative_to(self.home_dir)),
            "type": "directory" if resolved.is_dir() else "file",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "category": self.detect_file_type(resolved.name) if resolved.is_file() else None,
        }
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_filesystem.py::TestDetectFileType tests/test_filesystem.py::TestGetInfo -v
```

Expected: all passed.

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: filesystem service — path validation, directory listing, file type detection"
```

---

### Task 4: Filesystem Service — File CRUD and Security Hardening Tests

**Files:**
- Modify: `filebrowser/services/filesystem.py`
- Modify: `tests/test_filesystem.py`

#### Task 4a: File Read and get_file_path

**Step 1: Write the failing tests**

Append to `tests/test_filesystem.py`:

```python
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
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_filesystem.py::TestGetFilePath tests/test_filesystem.py::TestReadFile -v
```

**Step 3: Implement**

Add to `FilesystemService` in `filebrowser/services/filesystem.py`:

```python
    def get_file_path(self, path: str) -> Path:
        """Validate path and return resolved Path. Raises if not a file."""
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        if not resolved.is_file():
            raise IsADirectoryError(f"Not a file: {path}")
        return resolved

    def read_file(self, path: str) -> str:
        """Read and return text file content."""
        file_path = self.get_file_path(path)
        return file_path.read_text()
```

**Step 4: Run to verify pass**

```bash
python -m pytest tests/test_filesystem.py::TestGetFilePath tests/test_filesystem.py::TestReadFile -v
```

#### Task 4b: Delete, Mkdir, Rename

**Step 1: Write the failing tests**

Append to `tests/test_filesystem.py`:

```python
import shutil


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
        fs.mkdir("docs")  # already exists
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
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_filesystem.py::TestDelete tests/test_filesystem.py::TestMkdir tests/test_filesystem.py::TestRename -v
```

**Step 3: Implement**

Add these imports at the top of `filebrowser/services/filesystem.py`:

```python
import shutil
```

Add to `FilesystemService`:

```python
    def delete(self, path: str) -> None:
        """Delete a file or directory (recursive)."""
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        if resolved == self.home_dir:
            raise PermissionError("Cannot delete home directory")
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()

    def mkdir(self, path: str) -> Path:
        """Create a directory (and parents if needed)."""
        resolved = self.validate_path(path)
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def rename(self, old_path: str, new_path: str) -> Path:
        """Rename or move a file/directory."""
        old_resolved = self.validate_path(old_path)
        new_resolved = self.validate_path(new_path)
        if not old_resolved.exists():
            raise FileNotFoundError(f"Not found: {old_path}")
        old_resolved.rename(new_resolved)
        return new_resolved
```

**Step 4: Run to verify pass**

```bash
python -m pytest tests/test_filesystem.py::TestDelete tests/test_filesystem.py::TestMkdir tests/test_filesystem.py::TestRename -v
```

#### Task 4c: Security Hardening Tests

These tests verify path traversal prevention against various attack vectors.

**Step 1: Write security tests**

Append to `tests/test_filesystem.py`:

```python
import tempfile
import os


class TestSecurityPathTraversal:
    def test_dotdot_etc_passwd(self, fs):
        with pytest.raises(PermissionError):
            fs.validate_path("../../etc/passwd")

    def test_double_encoded_dotdot(self, fs):
        """Path with encoded dots — Python's Path resolves these literally."""
        with pytest.raises(PermissionError):
            fs.validate_path("..%2F..%2Fetc%2Fpasswd/../../../etc/passwd")

    def test_symlink_outside_home(self, fs, tmp_home):
        """Symlink pointing outside home_dir must be rejected."""
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, "secret.txt").write_text("secret data")
            link = tmp_home / "evil_link"
            link.symlink_to(outside)
            with pytest.raises(PermissionError):
                fs.validate_path("evil_link/secret.txt")

    def test_symlink_file_outside_home(self, fs, tmp_home):
        """Direct symlink to a file outside home."""
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
```

**Step 2: Run all security tests**

```bash
python -m pytest tests/test_filesystem.py::TestSecurityPathTraversal -v
```

Expected: all passed (the implementation already handles these cases via `relative_to` check).

**Step 3: Run full filesystem test suite**

```bash
python -m pytest tests/test_filesystem.py -v
```

Expected: all passed.

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: filesystem CRUD operations and security hardening tests"
```

---

## Phase 2: Auth

### Task 5: Auth Module

**Files:**
- Create: `filebrowser/auth.py`
- Create: `tests/test_auth.py`

#### Task 5a: Session Token Creation and Validation

**Step 1: Write the failing tests**

Create `tests/test_auth.py`:

```python
import time
import pytest


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
        # The username is the payload before the signature
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
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_auth.py -v
```

Expected: FAIL — functions don't exist.

**Step 3: Implement auth module**

Write `filebrowser/auth.py`:

```python
import pam
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from fastapi import Request, HTTPException
from filebrowser.config import settings


def authenticate_pam(username: str, password: str) -> bool:
    """Thin wrapper around PAM authentication."""
    p = pam.pam()
    return p.authenticate(username, password)


def create_session_token(username: str, secret_key: str) -> str:
    """Create a signed, timestamped session token."""
    signer = TimestampSigner(secret_key)
    return signer.sign(username).decode()


def validate_session_token(token: str, secret_key: str, max_age: int) -> str | None:
    """Validate a session token. Returns username or None if invalid/expired."""
    signer = TimestampSigner(secret_key)
    try:
        return signer.unsign(token, max_age=max_age).decode()
    except (BadSignature, SignatureExpired):
        return None


async def require_auth(request: Request) -> str:
    """FastAPI dependency: extract and validate session cookie."""
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "Not authenticated", "code": "UNAUTHORIZED"},
        )
    username = validate_session_token(token, settings.secret_key, settings.session_timeout)
    if not username:
        raise HTTPException(
            status_code=401,
            detail={"error": "Session expired or invalid", "code": "UNAUTHORIZED"},
        )
    return username
```

**Step 4: Run to verify pass**

```bash
python -m pytest tests/test_auth.py -v
```

Expected: all passed.

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: auth module with PAM wrapper and signed session tokens"
```

---

### Task 6: Auth Security Tests

**Files:**
- Modify: `tests/test_auth.py`

**Step 1: Write expiry and edge-case tests**

Append to `tests/test_auth.py`:

```python
class TestTokenExpiry:
    def test_expired_token_returns_none(self):
        from filebrowser.auth import create_session_token, validate_session_token

        token = create_session_token("alice", SECRET)
        # max_age=0 means the token is already expired
        result = validate_session_token(token, SECRET, max_age=0)
        assert result is None


class TestAuthenticatePam:
    def test_pam_function_exists(self):
        """Verify the PAM wrapper is importable and callable."""
        from filebrowser.auth import authenticate_pam

        assert callable(authenticate_pam)

    def test_pam_mock_success(self):
        """Mock PAM at the boundary to test the wrapper."""
        from unittest.mock import patch
        from filebrowser.auth import authenticate_pam

        with patch("filebrowser.auth.pam.pam") as mock_pam_class:
            mock_pam_class.return_value.authenticate.return_value = True
            assert authenticate_pam("user", "pass") is True

    def test_pam_mock_failure(self):
        from unittest.mock import patch
        from filebrowser.auth import authenticate_pam

        with patch("filebrowser.auth.pam.pam") as mock_pam_class:
            mock_pam_class.return_value.authenticate.return_value = False
            assert authenticate_pam("user", "wrong") is False


class TestRequireAuth:
    """Test the FastAPI dependency directly."""

    @pytest.mark.anyio
    async def test_missing_cookie_raises_401(self):
        from unittest.mock import MagicMock
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.cookies = {}
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_invalid_cookie_raises_401(self):
        from unittest.mock import MagicMock
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.cookies = {"session": "garbage-token"}
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(request)
        assert exc_info.value.status_code == 401
```

Note: The `@pytest.mark.anyio` tests require `anyio`. Add `pytest.importorskip("anyio")` at the top of the file if needed, or install it: `pip install anyio pytest-anyio`. Alternatively, you can replace these with synchronous tests using `asyncio.run()`:

Replace the `TestRequireAuth` class with this synchronous version if you prefer:

```python
import asyncio
from fastapi import HTTPException


class TestRequireAuth:
    def test_missing_cookie_raises_401(self):
        from unittest.mock import MagicMock
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.cookies = {}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert exc_info.value.status_code == 401

    def test_invalid_cookie_raises_401(self):
        from unittest.mock import MagicMock
        from filebrowser.auth import require_auth

        request = MagicMock()
        request.cookies = {"session": "garbage-token"}
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(require_auth(request))
        assert exc_info.value.status_code == 401
```

**Step 2: Run all auth tests**

```bash
python -m pytest tests/test_auth.py -v
```

Expected: all passed.

**Step 3: Commit**

```bash
git add -A && git commit -m "test: auth security tests — expiry, PAM mock, require_auth edge cases"
```

---

### Task 7: Auth Routes

**Files:**
- Create: `filebrowser/routes/auth.py`
- Modify: `tests/test_auth.py`

#### Task 7a: Login Endpoint

**Step 1: Write the failing test**

Append to `tests/test_auth.py`:

```python
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from filebrowser.routes.auth import router as auth_router


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
        assert response.json()["code"] == "AUTH_FAILED"

    def test_login_missing_fields(self, auth_client):
        response = auth_client.post("/api/auth/login", json={})
        assert response.status_code == 422
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_auth.py::TestLoginRoute -v
```

**Step 3: Implement auth routes**

Write `filebrowser/routes/auth.py`:

```python
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel
from filebrowser.auth import authenticate_pam, create_session_token, validate_session_token
from filebrowser.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    if not authenticate_pam(body.username, body.password):
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid credentials", "code": "AUTH_FAILED"},
        )
    token = create_session_token(body.username, settings.secret_key)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return {"username": body.username}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "Not authenticated", "code": "UNAUTHORIZED"},
        )
    username = validate_session_token(token, settings.secret_key, settings.session_timeout)
    if not username:
        raise HTTPException(
            status_code=401,
            detail={"error": "Session expired or invalid", "code": "UNAUTHORIZED"},
        )
    return {"username": username}
```

**Step 4: Run to verify pass**

```bash
python -m pytest tests/test_auth.py::TestLoginRoute -v
```

Expected: 3 passed.

#### Task 7b: Logout and Me Endpoints

**Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
class TestLogoutRoute:
    def test_logout_clears_cookie(self, auth_client):
        response = auth_client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json() == {"ok": True}


class TestMeRoute:
    def test_me_with_valid_session(self, auth_client):
        # Login first to get a session cookie
        with patch("filebrowser.routes.auth.authenticate_pam", return_value=True):
            auth_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "testpass"},
            )
        # Now /me should return the username
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
```

**Step 2: Run to verify pass** (already implemented above)

```bash
python -m pytest tests/test_auth.py::TestLogoutRoute tests/test_auth.py::TestMeRoute -v
```

Expected: all passed.

**Step 3: Run full auth test suite**

```bash
python -m pytest tests/test_auth.py -v
```

Expected: all passed.

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: auth routes — login, logout, me endpoints"
```

---

## Phase 3: File API

### Task 8: File Routes

**Files:**
- Create: `filebrowser/routes/files.py`

**Step 1: Implement all file routes**

Write `filebrowser/routes/files.py`:

```python
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from filebrowser.auth import require_auth
from filebrowser.services.filesystem import FilesystemService
from filebrowser.config import settings

router = APIRouter(prefix="/api/files", tags=["files"])


def get_fs() -> FilesystemService:
    """Dependency: provides FilesystemService scoped to home_dir."""
    return FilesystemService(settings.home_dir)


@router.get("")
async def list_directory(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        return fs.list_directory(path)
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Directory not found", "code": "NOT_FOUND"})
    except NotADirectoryError:
        raise HTTPException(status_code=400, detail={"error": "Not a directory", "code": "NOT_DIRECTORY"})


@router.get("/info")
async def file_info(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        return fs.get_info(path)
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"})


@router.get("/content")
async def get_content(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        file_path = fs.get_file_path(path)
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "File not found", "code": "NOT_FOUND"})
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail={"error": "Is a directory", "code": "IS_DIRECTORY"})
    return FileResponse(file_path)


@router.get("/download")
async def download_file(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        file_path = fs.get_file_path(path)
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "File not found", "code": "NOT_FOUND"})
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail={"error": "Is a directory", "code": "IS_DIRECTORY"})
    return FileResponse(file_path, filename=file_path.name)


@router.post("/upload")
async def upload_file(
    path: str = "",
    file: UploadFile = File(...),
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        dir_path = fs.validate_path(path)
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})

    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail={"error": "Not a directory", "code": "NOT_DIRECTORY"})

    # Sanitize filename — strip any path components
    safe_name = Path(file.filename).name
    if not safe_name:
        raise HTTPException(status_code=400, detail={"error": "Invalid filename", "code": "INVALID_FILENAME"})

    dest = dir_path / safe_name

    # Verify destination stays within home_dir
    try:
        dest.resolve().relative_to(fs.home_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})

    # Stream to disk with size limit
    size = 0
    try:
        with open(dest, "wb") as f:
            while chunk := await file.read(8192):
                size += len(chunk)
                if size > settings.upload_max_size:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail={"error": "File too large", "code": "FILE_TOO_LARGE"},
                    )
                f.write(chunk)
    except OSError as e:
        dest.unlink(missing_ok=True)
        if "No space left" in str(e):
            raise HTTPException(
                status_code=507,
                detail={"error": "Insufficient storage", "code": "INSUFFICIENT_STORAGE"},
            )
        raise

    return {"name": safe_name, "size": size}


@router.post("/mkdir")
async def make_directory(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        result = fs.mkdir(path)
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})
    return {"path": str(result.relative_to(fs.home_dir))}


class RenameRequest(BaseModel):
    old_path: str
    new_path: str


@router.put("/rename")
async def rename_file(
    body: RenameRequest,
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        result = fs.rename(body.old_path, body.new_path)
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"})
    return {"path": str(result.relative_to(fs.home_dir))}


@router.delete("")
async def delete_file(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        fs.delete(path)
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"})
    return {"ok": True}
```

**Step 2: Commit**

```bash
git add -A && git commit -m "feat: file API routes — list, info, content, download, upload, mkdir, rename, delete"
```

---

### Task 9: File Route Integration Tests

**Files:**
- Create: `tests/test_files.py`

**Step 1: Write integration tests**

Create `tests/test_files.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from filebrowser.routes.files import router as files_router, get_fs
from filebrowser.auth import require_auth
from filebrowser.services.filesystem import FilesystemService


@pytest.fixture
def client(tmp_home):
    """Authenticated test client with temp filesystem."""
    app = FastAPI()
    app.include_router(files_router)
    app.dependency_overrides[get_fs] = lambda: FilesystemService(tmp_home)
    app.dependency_overrides[require_auth] = lambda: "testuser"
    with TestClient(app) as c:
        yield c


@pytest.fixture
def unauth_client(tmp_home):
    """Unauthenticated test client — require_auth is NOT overridden."""
    app = FastAPI()
    app.include_router(files_router)
    app.dependency_overrides[get_fs] = lambda: FilesystemService(tmp_home)
    # require_auth is NOT overridden, so all requests need a valid session cookie
    with TestClient(app) as c:
        yield c


class TestListDirectory:
    def test_list_root(self, client):
        response = client.get("/api/files", params={"path": ""})
        assert response.status_code == 200
        names = [e["name"] for e in response.json()]
        assert "docs" in names
        assert "hello.txt" in names

    def test_list_subdirectory(self, client):
        response = client.get("/api/files", params={"path": "docs"})
        assert response.status_code == 200
        names = [e["name"] for e in response.json()]
        assert "readme.md" in names

    def test_list_nonexistent_returns_404(self, client):
        response = client.get("/api/files", params={"path": "nonexistent"})
        assert response.status_code == 404

    def test_list_traversal_returns_403(self, client):
        response = client.get("/api/files", params={"path": "../../etc"})
        assert response.status_code == 403


class TestFileInfo:
    def test_file_info(self, client):
        response = client.get("/api/files/info", params={"path": "hello.txt"})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "hello.txt"
        assert data["type"] == "file"
        assert data["category"] == "text"

    def test_info_not_found(self, client):
        response = client.get("/api/files/info", params={"path": "nope.txt"})
        assert response.status_code == 404


class TestFileContent:
    def test_read_text_file(self, client):
        response = client.get("/api/files/content", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert "Hello World" in response.text

    def test_content_not_found(self, client):
        response = client.get("/api/files/content", params={"path": "nope.txt"})
        assert response.status_code == 404

    def test_content_traversal_returns_403(self, client):
        response = client.get("/api/files/content", params={"path": "../../etc/passwd"})
        assert response.status_code == 403


class TestDownload:
    def test_download_sets_content_disposition(self, client):
        response = client.get("/api/files/download", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")


class TestUpload:
    def test_upload_file(self, client, tmp_home):
        response = client.post(
            "/api/files/upload",
            params={"path": ""},
            files={"file": ("uploaded.txt", b"file content", "text/plain")},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "uploaded.txt"
        assert (tmp_home / "uploaded.txt").read_text() == "file content"

    def test_upload_to_subdirectory(self, client, tmp_home):
        response = client.post(
            "/api/files/upload",
            params={"path": "docs"},
            files={"file": ("new.txt", b"new content", "text/plain")},
        )
        assert response.status_code == 200
        assert (tmp_home / "docs" / "new.txt").read_text() == "new content"

    def test_upload_to_nonexistent_dir_returns_error(self, client):
        response = client.post(
            "/api/files/upload",
            params={"path": "nonexistent"},
            files={"file": ("test.txt", b"data", "text/plain")},
        )
        assert response.status_code in (400, 404)


class TestMkdir:
    def test_create_directory(self, client, tmp_home):
        response = client.post("/api/files/mkdir", params={"path": "new_folder"})
        assert response.status_code == 200
        assert (tmp_home / "new_folder").is_dir()


class TestRename:
    def test_rename_file(self, client, tmp_home):
        response = client.put(
            "/api/files/rename",
            json={"old_path": "hello.txt", "new_path": "renamed.txt"},
        )
        assert response.status_code == 200
        assert not (tmp_home / "hello.txt").exists()
        assert (tmp_home / "renamed.txt").exists()

    def test_rename_nonexistent_returns_404(self, client):
        response = client.put(
            "/api/files/rename",
            json={"old_path": "nonexistent.txt", "new_path": "other.txt"},
        )
        assert response.status_code == 404


class TestDelete:
    def test_delete_file(self, client, tmp_home):
        response = client.delete("/api/files", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert not (tmp_home / "hello.txt").exists()

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete("/api/files", params={"path": "nope.txt"})
        assert response.status_code == 404

    def test_delete_traversal_returns_403(self, client):
        response = client.delete("/api/files", params={"path": "../../etc/passwd"})
        assert response.status_code == 403


class TestAuthEnforcement:
    def test_list_requires_auth(self, unauth_client):
        response = unauth_client.get("/api/files", params={"path": ""})
        assert response.status_code == 401

    def test_content_requires_auth(self, unauth_client):
        response = unauth_client.get("/api/files/content", params={"path": "hello.txt"})
        assert response.status_code == 401

    def test_upload_requires_auth(self, unauth_client):
        response = unauth_client.post(
            "/api/files/upload",
            params={"path": ""},
            files={"file": ("test.txt", b"data", "text/plain")},
        )
        assert response.status_code == 401

    def test_delete_requires_auth(self, unauth_client):
        response = unauth_client.delete("/api/files", params={"path": "hello.txt"})
        assert response.status_code == 401
```

**Step 2: Run all file route tests**

```bash
python -m pytest tests/test_files.py -v
```

Expected: all passed.

**Step 3: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests across all files pass.

**Step 4: Commit**

```bash
git add -A && git commit -m "test: file route integration tests — CRUD, auth enforcement, error cases"
```

---

### Task 10: Main App Assembly

**Files:**
- Create: `filebrowser/main.py`

**Step 1: Implement the main app**

Write `filebrowser/main.py`:

```python
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from filebrowser.routes import auth, files

app = FastAPI(title="File Browser", docs_url=None, redoc_url=None)

# --- Error handlers ---


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
    )


# --- Routers ---

app.include_router(auth.router)
app.include_router(files.router)

# --- Static files (must be last so API routes take priority) ---

static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

**Step 2: Verify the app starts**

```bash
cd /Users/robotdad/Source/filebrowser
# Create a minimal index.html so static mount works
echo "<h1>File Browser</h1>" > filebrowser/static/index.html
uvicorn filebrowser.main:app --reload
```

Expected: server starts on http://127.0.0.1:8000. Visiting it shows "File Browser". Press Ctrl+C to stop.

**Step 3: Run full test suite to verify nothing broke**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: main app — mounts routers, static files, global error handler"
```

---

## Phase 4: Frontend

Frontend tasks produce static files. There is no build step. Verify each task by running `uvicorn filebrowser.main:app --reload` and checking the browser at `http://127.0.0.1:8000`.

### Task 11: HTML Shell

**Files:**
- Create: `filebrowser/static/index.html`

**Step 1: Write `index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Browser</title>
    <link rel="stylesheet" href="/css/styles.css">
    <link rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/highlight.js@11/styles/github.min.css"
          media="(prefers-color-scheme: light)">
    <link rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/highlight.js@11/styles/github-dark.min.css"
          media="(prefers-color-scheme: dark)">
    <script type="importmap">
    {
        "imports": {
            "preact": "https://esm.sh/preact@10",
            "preact/hooks": "https://esm.sh/preact@10/hooks",
            "htm": "https://esm.sh/htm@3",
            "highlight.js": "https://esm.sh/highlight.js@11",
            "marked": "https://esm.sh/marked@15"
        }
    }
    </script>
</head>
<body>
    <div id="app"></div>
    <script type="module" src="/js/app.js"></script>
</body>
</html>
```

**Step 2: Verify**

Run `uvicorn filebrowser.main:app --reload` and visit `http://127.0.0.1:8000`. You should see a blank page with no console errors (the app.js doesn't exist yet — just confirm the HTML loads and the import map is valid by checking the Network tab).

**Step 3: Commit**

```bash
git add -A && git commit -m "feat: HTML shell with import map for Preact, HTM, highlight.js, marked"
```

---

### Task 12: CSS

**Files:**
- Create: `filebrowser/static/css/styles.css`

**Step 1: Write the stylesheet**

Create `filebrowser/static/css/styles.css`:

```css
/* === Custom Properties === */
:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f5f5f5;
    --bg-tertiary: #e8e8e8;
    --text-primary: #1a1a1a;
    --text-secondary: #555555;
    --text-muted: #888888;
    --border-color: #ddd;
    --accent: #0066cc;
    --accent-hover: #0055aa;
    --danger: #cc3333;
    --danger-hover: #aa2222;
    --success: #28a745;
    --sidebar-width: 280px;
    --header-height: 48px;
    --action-bar-height: 48px;
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg-primary: #1e1e1e;
        --bg-secondary: #252525;
        --bg-tertiary: #333333;
        --text-primary: #e0e0e0;
        --text-secondary: #aaaaaa;
        --text-muted: #777777;
        --border-color: #444;
        --accent: #4da6ff;
        --accent-hover: #80bfff;
        --danger: #ff5555;
        --danger-hover: #ff7777;
        --success: #5cb85c;
    }
}

/* === Reset === */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    height: 100vh;
    overflow: hidden;
}

#app { height: 100vh; }

/* === Layout === */
.layout {
    display: grid;
    grid-template-rows: var(--header-height) 1fr var(--action-bar-height);
    height: 100vh;
}

.main-content {
    display: grid;
    grid-template-columns: var(--sidebar-width) 1fr;
    overflow: hidden;
    position: relative;
}

/* === Header === */
.header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 16px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
}

.header-right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 12px;
}

.username { color: var(--text-secondary); font-size: 14px; }

.logout-btn {
    background: none;
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    padding: 4px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
}
.logout-btn:hover { color: var(--danger); border-color: var(--danger); }

.hamburger {
    display: none;
    background: none;
    border: none;
    font-size: 20px;
    cursor: pointer;
    color: var(--text-primary);
    padding: 4px 8px;
}

/* === Sidebar === */
.sidebar {
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    overflow-y: auto;
    padding: 8px 0;
}

.sidebar-overlay {
    display: none;
}

/* === File Tree === */
.tree-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    cursor: pointer;
    font-size: 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.tree-item:hover { background: var(--bg-tertiary); }
.tree-item.selected { background: var(--accent); color: #fff; }
.tree-icon { font-size: 14px; flex-shrink: 0; }

/* === Preview === */
.preview {
    overflow: auto;
    padding: 16px;
}

.preview-empty, .preview-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-muted);
    font-size: 16px;
}

.text-viewer, .code-viewer {
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    font-size: 13px;
    line-height: 1.5;
}

.text-viewer pre, .code-viewer pre {
    margin: 0;
    overflow-x: auto;
}

.line { display: flex; }
.line-number {
    display: inline-block;
    min-width: 3em;
    text-align: right;
    padding-right: 12px;
    color: var(--text-muted);
    user-select: none;
    flex-shrink: 0;
}
.line-content { white-space: pre; }

.markdown-viewer {
    max-width: 800px;
    line-height: 1.7;
}
.markdown-viewer h1, .markdown-viewer h2, .markdown-viewer h3 { margin-top: 1em; }
.markdown-viewer p { margin: 0.5em 0; }
.markdown-viewer code {
    background: var(--bg-tertiary);
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
}
.markdown-viewer pre code { display: block; padding: 12px; overflow-x: auto; }

.preview-image img { max-width: 100%; max-height: 80vh; }
.preview-audio, .preview-video { display: flex; justify-content: center; padding: 24px; }
.preview-video video { max-width: 100%; max-height: 80vh; }
.preview-pdf iframe { width: 100%; height: calc(100vh - 140px); border: none; }
.preview-other { padding: 24px; }

.download-btn {
    display: inline-block;
    margin-top: 12px;
    padding: 8px 16px;
    background: var(--accent);
    color: #fff;
    text-decoration: none;
    border-radius: 4px;
}
.download-btn:hover { background: var(--accent-hover); }

/* === Breadcrumb === */
.breadcrumb {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 14px;
    overflow: hidden;
}
.breadcrumb-item {
    cursor: pointer;
    color: var(--accent);
    white-space: nowrap;
}
.breadcrumb-item:hover { text-decoration: underline; }
.breadcrumb-sep { color: var(--text-muted); }

/* === Action Bar === */
.action-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 16px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
}

.action-bar button {
    padding: 6px 14px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
    cursor: pointer;
    font-size: 13px;
}
.action-bar button:hover { background: var(--bg-tertiary); }
.action-bar button.danger { color: var(--danger); border-color: var(--danger); }
.action-bar button.danger:hover { background: var(--danger); color: #fff; }

.action-bar input {
    padding: 4px 8px;
    border: 1px solid var(--accent);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 13px;
}

/* === Login === */
.login-container {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100vh;
    background: var(--bg-secondary);
}

.login-form {
    background: var(--bg-primary);
    padding: 32px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    width: 320px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}
.login-form h1 { font-size: 20px; text-align: center; margin-bottom: 8px; }
.login-form input {
    padding: 10px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 14px;
    background: var(--bg-primary);
    color: var(--text-primary);
}
.login-form button {
    padding: 10px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 4px;
    font-size: 14px;
    cursor: pointer;
}
.login-form button:hover { background: var(--accent-hover); }
.login-form button:disabled { opacity: 0.6; cursor: not-allowed; }
.login-form .error {
    background: var(--danger);
    color: #fff;
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 13px;
    text-align: center;
}

/* === Modal === */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
}

.modal {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 24px;
    width: 400px;
    max-width: 90vw;
    display: flex;
    flex-direction: column;
    gap: 12px;
}
.modal h2 { font-size: 18px; }

.drop-zone {
    border: 2px dashed var(--border-color);
    border-radius: 8px;
    padding: 32px;
    text-align: center;
    color: var(--text-muted);
}
.drop-zone.dragging { border-color: var(--accent); color: var(--accent); }

.upload-progress { font-size: 13px; color: var(--text-secondary); }

/* === Toast === */
.toast {
    position: fixed;
    top: 16px;
    right: 16px;
    padding: 12px 20px;
    border-radius: 6px;
    font-size: 14px;
    z-index: 200;
    animation: toast-in 0.3s ease;
}
.toast-error { background: var(--danger); color: #fff; }
@keyframes toast-in { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; } }

/* === Loading === */
.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100vh;
    color: var(--text-muted);
}

/* === Responsive: Mobile (<768px) === */
@media (max-width: 768px) {
    .main-content { grid-template-columns: 1fr; }

    .hamburger { display: block; }

    .sidebar {
        position: fixed;
        top: var(--header-height);
        left: 0;
        bottom: var(--action-bar-height);
        width: var(--sidebar-width);
        z-index: 50;
        transform: translateX(-100%);
        transition: transform 0.25s ease;
    }
    .sidebar.open { transform: translateX(0); }

    .sidebar-overlay {
        display: block;
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.3);
        z-index: 49;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.25s ease;
    }
    .sidebar-overlay.visible { opacity: 1; pointer-events: auto; }
}
```

**Step 2: Verify** — reload browser, confirm CSS loads and dark/light mode works.

**Step 3: Commit**

```bash
git add -A && git commit -m "feat: CSS with custom properties, two-panel layout, dark mode, responsive"
```

---

### Task 13: api.js

**Files:**
- Create: `filebrowser/static/js/api.js`

**Step 1: Write the fetch wrapper**

```javascript
class ApiClient {
    async request(url, options = {}) {
        const response = await fetch(url, {
            credentials: 'same-origin',
            ...options,
        });

        if (response.status === 401) {
            window.dispatchEvent(new CustomEvent('auth:logout'));
            throw new Error('Unauthorized');
        }

        if (!response.ok) {
            const body = await response.json().catch(() => ({ error: response.statusText }));
            this.showToast(body.error || 'An error occurred');
            throw new Error(body.error || response.statusText);
        }

        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        }
        return response.text();
    }

    get(url) {
        return this.request(url);
    }

    post(url, body) {
        const isFormData = body instanceof FormData;
        return this.request(url, {
            method: 'POST',
            headers: isFormData ? {} : { 'Content-Type': 'application/json' },
            body: isFormData ? body : JSON.stringify(body),
        });
    }

    put(url, body) {
        return this.request(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    }

    del(url) {
        return this.request(url, { method: 'DELETE' });
    }

    showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'toast toast-error';
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }
}

export const api = new ApiClient();
```

**Step 2: Commit**

```bash
git add -A && git commit -m "feat: api.js fetch wrapper with auth handling and toast errors"
```

---

### Task 14: Login + App Entry Point

**Files:**
- Create: `filebrowser/static/js/html.js`
- Create: `filebrowser/static/js/components/login.js`
- Create: `filebrowser/static/js/app.js`

**Step 1: Create shared html helper**

Create `filebrowser/static/js/html.js`:

```javascript
import { h } from 'preact';
import htm from 'htm';

export const html = htm.bind(h);
export { h };
```

**Step 2: Create LoginForm component**

Create `filebrowser/static/js/components/login.js`:

```javascript
import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';

export function LoginForm({ onLogin }) {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            const data = await api.post('/api/auth/login', { username, password });
            onLogin(data.username);
        } catch {
            setError('Invalid username or password');
        } finally {
            setLoading(false);
        }
    };

    return html`
        <div class="login-container">
            <form class="login-form" onSubmit=${handleSubmit}>
                <h1>File Browser</h1>
                ${error && html`<div class="error">${error}</div>`}
                <input
                    type="text"
                    placeholder="Username"
                    value=${username}
                    onInput=${(e) => setUsername(e.target.value)}
                    required
                    autocomplete="username"
                />
                <input
                    type="password"
                    placeholder="Password"
                    value=${password}
                    onInput=${(e) => setPassword(e.target.value)}
                    required
                    autocomplete="current-password"
                />
                <button type="submit" disabled=${loading}>
                    ${loading ? 'Signing in...' : 'Sign In'}
                </button>
            </form>
        </div>
    `;
}
```

**Step 3: Create App entry point**

Create `filebrowser/static/js/app.js`:

```javascript
import { render } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import { html } from './html.js';
import { api } from './api.js';
import { LoginForm } from './components/login.js';
import { Layout } from './components/layout.js';

function App() {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get('/api/auth/me')
            .then((data) => setUser(data.username))
            .catch(() => setUser(null))
            .finally(() => setLoading(false));

        const handleLogout = () => setUser(null);
        window.addEventListener('auth:logout', handleLogout);
        return () => window.removeEventListener('auth:logout', handleLogout);
    }, []);

    if (loading) return html`<div class="loading">Loading...</div>`;
    if (!user) return html`<${LoginForm} onLogin=${(u) => setUser(u)} />`;
    return html`<${Layout} username=${user} onLogout=${() => setUser(null)} />`;
}

render(html`<${App} />`, document.getElementById('app'));
```

**Step 4: Verify** — run `uvicorn filebrowser.main:app --reload`. Browser should show the login form (since you're not authenticated). Submitting with valid Linux credentials should log you in (though Layout component doesn't exist yet — you'll see an error in the console which is expected).

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: login form and app entry point with auth state management"
```

---

### Task 15: Layout + File Tree

**Files:**
- Create: `filebrowser/static/js/components/layout.js`
- Create: `filebrowser/static/js/components/tree.js`

**Step 1: Create FileTree component**

Create `filebrowser/static/js/components/tree.js`:

```javascript
import { useState, useEffect } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';

export function FileTree({ currentPath, onNavigate, onSelectFile, refreshKey }) {
    const [entries, setEntries] = useState({});
    const [expanded, setExpanded] = useState({});
    const [selected, setSelected] = useState(null);

    useEffect(() => {
        loadDirectory('');
    }, [refreshKey]);

    const loadDirectory = async (path) => {
        try {
            const data = await api.get(`/api/files?path=${encodeURIComponent(path)}`);
            setEntries((prev) => ({ ...prev, [path]: data }));
        } catch {
            // toast is shown by api.js
        }
    };

    const toggleFolder = (path) => {
        setExpanded((prev) => {
            const next = { ...prev };
            if (next[path]) {
                delete next[path];
            } else {
                next[path] = true;
                loadDirectory(path);
            }
            return next;
        });
        onNavigate(path);
    };

    const selectFile = (path) => {
        setSelected(path);
        onSelectFile(path);
    };

    const renderEntries = (path, depth = 0) => {
        const items = entries[path] || [];
        return items.map((item) => {
            const itemPath = path ? `${path}/${item.name}` : item.name;
            if (item.type === 'directory') {
                return html`
                    <div key=${itemPath}>
                        <div
                            class="tree-item tree-folder ${expanded[itemPath] ? 'expanded' : ''}"
                            style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                            onClick=${() => toggleFolder(itemPath)}
                        >
                            <span class="tree-icon">${expanded[itemPath] ? '\u{1F4C2}' : '\u{1F4C1}'}</span>
                            ${item.name}
                        </div>
                        ${expanded[itemPath] && renderEntries(itemPath, depth + 1)}
                    </div>
                `;
            }
            return html`
                <div
                    key=${itemPath}
                    class="tree-item tree-file ${selected === itemPath ? 'selected' : ''}"
                    style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                    onClick=${() => selectFile(itemPath)}
                >
                    <span class="tree-icon">\u{1F4C4}</span>
                    ${item.name}
                </div>
            `;
        });
    };

    return html`<div class="file-tree">${renderEntries('')}</div>`;
}
```

**Step 2: Create Layout component**

Create `filebrowser/static/js/components/layout.js`:

```javascript
import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { Breadcrumb } from './breadcrumb.js';
import { FileTree } from './tree.js';
import { PreviewPane } from './preview.js';
import { ActionBar } from './actions.js';

export function Layout({ username, onLogout }) {
    const [currentPath, setCurrentPath] = useState('');
    const [selectedFile, setSelectedFile] = useState(null);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    const refresh = () => setRefreshKey((k) => k + 1);

    const handleLogout = async () => {
        await api.post('/api/auth/logout');
        onLogout();
    };

    const handleNavigate = (path) => {
        setCurrentPath(path);
        setSidebarOpen(false);
    };

    const handleSelectFile = (path) => {
        setSelectedFile(path);
        setSidebarOpen(false);
    };

    return html`
        <div class="layout">
            <header class="header">
                <button class="hamburger" onClick=${() => setSidebarOpen(!sidebarOpen)}>\u2630</button>
                <${Breadcrumb} path=${currentPath} onNavigate=${setCurrentPath} />
                <div class="header-right">
                    <span class="username">${username}</span>
                    <button class="logout-btn" onClick=${handleLogout}>Logout</button>
                </div>
            </header>
            <div class="main-content">
                <aside class="sidebar ${sidebarOpen ? 'open' : ''}">
                    <${FileTree}
                        currentPath=${currentPath}
                        onNavigate=${handleNavigate}
                        onSelectFile=${handleSelectFile}
                        refreshKey=${refreshKey}
                    />
                </aside>
                <div
                    class="sidebar-overlay ${sidebarOpen ? 'visible' : ''}"
                    onClick=${() => setSidebarOpen(false)}
                ></div>
                <main class="preview">
                    <${PreviewPane} filePath=${selectedFile} />
                </main>
            </div>
            <${ActionBar}
                currentPath=${currentPath}
                selectedFile=${selectedFile}
                onRefresh=${refresh}
            />
        </div>
    `;
}
```

**Step 3: Verify** — won't fully render yet (missing breadcrumb, preview, actions). That's expected. Proceed to the next tasks.

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: layout shell and recursive file tree with lazy loading"
```

---

### Task 16: Breadcrumb

**Files:**
- Create: `filebrowser/static/js/components/breadcrumb.js`

**Step 1: Write the component**

```javascript
import { html } from '../html.js';

export function Breadcrumb({ path, onNavigate }) {
    const parts = path ? path.split('/') : [];

    return html`
        <nav class="breadcrumb">
            <span class="breadcrumb-item" onClick=${() => onNavigate('')}>Home</span>
            ${parts.map((part, i) => {
                const partPath = parts.slice(0, i + 1).join('/');
                return html`
                    <span class="breadcrumb-sep">/</span>
                    <span class="breadcrumb-item" onClick=${() => onNavigate(partPath)}>
                        ${part}
                    </span>
                `;
            })}
        </nav>
    `;
}
```

**Step 2: Commit**

```bash
git add -A && git commit -m "feat: breadcrumb navigation component"
```

---

### Task 17: Preview Pane

**Files:**
- Create: `filebrowser/static/js/components/preview.js`

**Step 1: Write the component**

```javascript
import { useState, useEffect, useRef, useMemo } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import hljs from 'highlight.js';
import { marked } from 'marked';

const FILE_TYPES = {
    text: ['.txt', '.log', '.csv', '.json', '.xml', '.yaml', '.yml', '.toml', '.env', '.conf'],
    code: ['.py', '.js', '.ts', '.go', '.rs', '.c', '.cpp', '.java', '.sh', '.sql', '.html', '.css'],
    markdown: ['.md'],
    image: ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'],
    audio: ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'],
    video: ['.mp4', '.webm', '.mkv', '.mov', '.avi'],
    pdf: ['.pdf'],
};

function getFileType(path) {
    const dot = path.lastIndexOf('.');
    if (dot === -1) return 'other';
    const ext = path.slice(dot).toLowerCase();
    for (const [type, exts] of Object.entries(FILE_TYPES)) {
        if (exts.includes(ext)) return type;
    }
    return 'other';
}

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(1)} GB`;
}

function TextViewer({ text }) {
    const lines = text.split('\n');
    return html`
        <div class="text-viewer">
            <pre><code>${lines.map(
                (line, i) => html`<div class="line"><span class="line-number">${i + 1}</span><span class="line-content">${line}</span></div>`
            )}</code></pre>
        </div>
    `;
}

function CodeViewer({ text, path }) {
    const codeRef = useRef(null);

    useEffect(() => {
        if (codeRef.current) {
            codeRef.current.textContent = text;
            hljs.highlightElement(codeRef.current);
        }
    }, [text]);

    const ext = path.split('.').pop();
    const langMap = { py: 'python', js: 'javascript', ts: 'typescript', rs: 'rust', sh: 'bash', yml: 'yaml' };
    const lang = langMap[ext] || ext;

    return html`
        <div class="code-viewer">
            <pre><code ref=${codeRef} class="language-${lang}">${text}</code></pre>
        </div>
    `;
}

function MarkdownViewer({ text }) {
    const htmlContent = useMemo(() => marked.parse(text), [text]);
    return html`<div class="markdown-viewer" dangerouslySetInnerHTML=${{ __html: htmlContent }}></div>`;
}

export function PreviewPane({ filePath }) {
    const [content, setContent] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!filePath) {
            setContent(null);
            return;
        }

        const type = getFileType(filePath);
        setLoading(true);

        if (['text', 'code', 'markdown'].includes(type)) {
            api.get(`/api/files/content?path=${encodeURIComponent(filePath)}`)
                .then((text) => setContent({ type, text }))
                .catch(() => setContent(null))
                .finally(() => setLoading(false));
        } else {
            api.get(`/api/files/info?path=${encodeURIComponent(filePath)}`)
                .then((info) => setContent({ type, info }))
                .catch(() => setContent(null))
                .finally(() => setLoading(false));
        }
    }, [filePath]);

    if (!filePath) return html`<div class="preview-empty">Select a file to preview</div>`;
    if (loading) return html`<div class="preview-loading">Loading...</div>`;
    if (!content) return html`<div class="preview-empty">Unable to load file</div>`;

    const contentUrl = `/api/files/content?path=${encodeURIComponent(filePath)}`;
    const downloadUrl = `/api/files/download?path=${encodeURIComponent(filePath)}`;

    switch (content.type) {
        case 'text':
            return html`<${TextViewer} text=${content.text} />`;
        case 'code':
            return html`<${CodeViewer} text=${content.text} path=${filePath} />`;
        case 'markdown':
            return html`<${MarkdownViewer} text=${content.text} />`;
        case 'image':
            return html`<div class="preview-image"><img src=${contentUrl} alt=${filePath} /></div>`;
        case 'audio':
            return html`<div class="preview-audio"><audio controls src=${contentUrl}></audio></div>`;
        case 'video':
            return html`<div class="preview-video"><video controls src=${contentUrl}></video></div>`;
        case 'pdf':
            return html`<div class="preview-pdf"><iframe src=${contentUrl}></iframe></div>`;
        default:
            return html`
                <div class="preview-other">
                    <h3>${filePath.split('/').pop()}</h3>
                    ${content.info && html`<p>Size: ${formatSize(content.info.size)}</p>`}
                    ${content.info && html`<p>Modified: ${content.info.modified}</p>`}
                    <a href=${downloadUrl} class="download-btn">Download</a>
                </div>
            `;
    }
}
```

**Step 2: Verify** — run server, log in, click a text file. It should render with line numbers.

**Step 3: Commit**

```bash
git add -A && git commit -m "feat: preview pane with text, code, markdown, media, and PDF viewers"
```

---

### Task 18: Actions + Upload

**Files:**
- Create: `filebrowser/static/js/components/actions.js`
- Create: `filebrowser/static/js/components/upload.js`

**Step 1: Create UploadModal component**

Create `filebrowser/static/js/components/upload.js`:

```javascript
import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';

export function UploadModal({ path, onClose, onUploaded }) {
    const [dragging, setDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState('');

    const uploadFile = async (file) => {
        setUploading(true);
        setProgress(`Uploading ${file.name}...`);
        try {
            const formData = new FormData();
            formData.append('file', file);
            await api.post(`/api/files/upload?path=${encodeURIComponent(path)}`, formData);
            setProgress(`${file.name} uploaded!`);
            onUploaded();
        } catch {
            setProgress('Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragging(false);
        if (e.dataTransfer.files.length > 0) {
            uploadFile(e.dataTransfer.files[0]);
        }
    };

    const handleFileInput = (e) => {
        if (e.target.files.length > 0) {
            uploadFile(e.target.files[0]);
        }
    };

    return html`
        <div class="modal-overlay" onClick=${onClose}>
            <div class="modal" onClick=${(e) => e.stopPropagation()}>
                <h2>Upload File</h2>
                <div
                    class="drop-zone ${dragging ? 'dragging' : ''}"
                    onDragOver=${(e) => { e.preventDefault(); setDragging(true); }}
                    onDragLeave=${() => setDragging(false)}
                    onDrop=${handleDrop}
                >
                    <p>Drag and drop a file here, or</p>
                    <input type="file" onChange=${handleFileInput} />
                </div>
                ${progress && html`<p class="upload-progress">${progress}</p>`}
                <button onClick=${onClose} disabled=${uploading}>Close</button>
            </div>
        </div>
    `;
}
```

**Step 2: Create ActionBar component**

Create `filebrowser/static/js/components/actions.js`:

```javascript
import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { UploadModal } from './upload.js';

export function ActionBar({ currentPath, selectedFile, onRefresh }) {
    const [showUpload, setShowUpload] = useState(false);
    const [renaming, setRenaming] = useState(false);
    const [newName, setNewName] = useState('');

    const handleNewFolder = async () => {
        const name = prompt('Folder name:');
        if (!name) return;
        const path = currentPath ? `${currentPath}/${name}` : name;
        try {
            await api.post(`/api/files/mkdir?path=${encodeURIComponent(path)}`);
            onRefresh();
        } catch {
            // toast shown by api.js
        }
    };

    const handleDelete = async () => {
        if (!selectedFile) return;
        if (!confirm(`Delete ${selectedFile}?`)) return;
        try {
            await api.del(`/api/files?path=${encodeURIComponent(selectedFile)}`);
            onRefresh();
        } catch {
            // toast shown by api.js
        }
    };

    const startRename = () => {
        if (!selectedFile) return;
        setNewName(selectedFile.split('/').pop());
        setRenaming(true);
    };

    const handleRename = async () => {
        if (!selectedFile || !newName) return;
        const parts = selectedFile.split('/');
        parts[parts.length - 1] = newName;
        const newPath = parts.join('/');
        try {
            await api.put('/api/files/rename', { old_path: selectedFile, new_path: newPath });
            setRenaming(false);
            setNewName('');
            onRefresh();
        } catch {
            // toast shown by api.js
        }
    };

    return html`
        <div class="action-bar">
            <button onClick=${() => setShowUpload(true)}>Upload</button>
            <button onClick=${handleNewFolder}>New Folder</button>
            ${selectedFile && !renaming && html`
                <button onClick=${startRename}>Rename</button>
                <button class="danger" onClick=${handleDelete}>Delete</button>
            `}
            ${renaming && html`
                <input
                    value=${newName}
                    onInput=${(e) => setNewName(e.target.value)}
                    onKeyDown=${(e) => e.key === 'Enter' && handleRename()}
                />
                <button onClick=${handleRename}>Save</button>
                <button onClick=${() => setRenaming(false)}>Cancel</button>
            `}
            ${showUpload && html`
                <${UploadModal}
                    path=${currentPath}
                    onClose=${() => setShowUpload(false)}
                    onUploaded=${() => { setShowUpload(false); onRefresh(); }}
                />
            `}
        </div>
    `;
}
```

**Step 3: Verify** — run server, log in. Full two-panel UI should render. Test:
- Click folders to expand them in the tree
- Click files to preview them
- Click "Upload" to open the modal
- Click "New Folder" to create a directory
- Select a file, click "Rename" to rename it
- Select a file, click "Delete" to remove it
- Resize browser below 768px to see mobile drawer behavior

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: action bar with upload, new folder, rename, delete"
```

---

## Phase 5: Deployment

### Task 19: systemd Unit File

**Files:**
- Create: `deploy/filebrowser.service`

**Step 1: Write the service file**

Create `deploy/filebrowser.service`:

```ini
[Unit]
Description=File Browser
After=network.target tailscaled.service
Wants=tailscaled.service

[Service]
Type=simple
User=FILEBROWSER_USER
WorkingDirectory=FILEBROWSER_DIR
ExecStart=FILEBROWSER_DIR/.venv/bin/uvicorn filebrowser.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
Environment=FILEBROWSER_SECRET_KEY=FILEBROWSER_SECRET

[Install]
WantedBy=multi-user.target
```

Placeholders (`FILEBROWSER_USER`, `FILEBROWSER_DIR`, `FILEBROWSER_SECRET`) are replaced by `install.sh` at deploy time.

**Step 2: Commit**

```bash
git add -A && git commit -m "feat: systemd service unit for filebrowser"
```

---

### Task 20: Caddyfile + Cert Renewal Timer

**Files:**
- Create: `deploy/Caddyfile.template`
- Create: `deploy/tailscale-cert-renew.service`
- Create: `deploy/tailscale-cert-renew.timer`

**Step 1: Write Caddyfile template**

Create `deploy/Caddyfile.template`:

```
FILEBROWSER_FQDN {
    tls CERT_PATH KEY_PATH
    reverse_proxy localhost:8000
}
```

**Step 2: Write cert renewal service**

Create `deploy/tailscale-cert-renew.service`:

```ini
[Unit]
Description=Renew Tailscale TLS certificates

[Service]
Type=oneshot
ExecStart=/usr/bin/tailscale cert --cert-file CERT_PATH --key-file KEY_PATH FILEBROWSER_FQDN
```

**Step 3: Write cert renewal timer**

Create `deploy/tailscale-cert-renew.timer`:

```ini
[Unit]
Description=Weekly Tailscale cert renewal

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
```

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: Caddyfile template and cert renewal systemd timer"
```

---

### Task 21: Install Script

**Files:**
- Create: `deploy/install.sh`

**Step 1: Write the install script**

Create `deploy/install.sh`:

```bash
#!/bin/bash
set -euo pipefail

echo "=== File Browser Installer ==="

# --- Detect environment ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
USER="$(whoami)"
INSTALL_DIR="/opt/filebrowser"
CERT_DIR="/etc/ssl/tailscale"

# --- Detect Tailscale FQDN ---
echo "Detecting Tailscale FQDN..."
FQDN=$(tailscale status --json | python3 -c "import sys, json; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))")
echo "  FQDN: $FQDN"

CERT_PATH="$CERT_DIR/$FQDN.crt"
KEY_PATH="$CERT_DIR/$FQDN.key"

# --- Generate secret key (only if not already set) ---
SECRET_FILE="$INSTALL_DIR/.secret_key"
if [ -f "$SECRET_FILE" ]; then
    SECRET_KEY=$(cat "$SECRET_FILE")
    echo "  Using existing secret key"
else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "  Generated new secret key"
fi

# --- Install application ---
echo "Installing application to $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$USER:$USER" "$INSTALL_DIR"
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.git' "$PROJECT_DIR/" "$INSTALL_DIR/"

# Save secret key
echo "$SECRET_KEY" > "$SECRET_FILE"
chmod 600 "$SECRET_FILE"

# --- Create venv and install ---
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"

# --- Generate Tailscale cert ---
echo "Generating Tailscale certificate..."
sudo mkdir -p "$CERT_DIR"
sudo tailscale cert --cert-file "$CERT_PATH" --key-file "$KEY_PATH" "$FQDN"

# --- Install Caddy ---
if ! command -v caddy &>/dev/null; then
    echo "Installing Caddy..."
    sudo apt-get update -qq && sudo apt-get install -y -qq caddy
else
    echo "Caddy already installed"
fi

# --- Write config files from templates ---
echo "Writing configuration files..."

sudo sed \
    -e "s|FILEBROWSER_FQDN|$FQDN|g" \
    -e "s|CERT_PATH|$CERT_PATH|g" \
    -e "s|KEY_PATH|$KEY_PATH|g" \
    "$INSTALL_DIR/deploy/Caddyfile.template" \
    | sudo tee /etc/caddy/Caddyfile > /dev/null

sudo sed \
    -e "s|FILEBROWSER_USER|$USER|g" \
    -e "s|FILEBROWSER_DIR|$INSTALL_DIR|g" \
    -e "s|FILEBROWSER_SECRET|$SECRET_KEY|g" \
    "$INSTALL_DIR/deploy/filebrowser.service" \
    | sudo tee /etc/systemd/system/filebrowser.service > /dev/null

sudo sed \
    -e "s|CERT_PATH|$CERT_PATH|g" \
    -e "s|KEY_PATH|$KEY_PATH|g" \
    -e "s|FILEBROWSER_FQDN|$FQDN|g" \
    "$INSTALL_DIR/deploy/tailscale-cert-renew.service" \
    | sudo tee /etc/systemd/system/tailscale-cert-renew.service > /dev/null

sudo cp "$INSTALL_DIR/deploy/tailscale-cert-renew.timer" \
    /etc/systemd/system/tailscale-cert-renew.timer

# --- Enable and start services ---
echo "Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable --now filebrowser
sudo systemctl enable --now caddy
sudo systemctl enable --now tailscale-cert-renew.timer

echo ""
echo "=== Installation complete ==="
echo "File Browser is running at: https://$FQDN"
echo ""
echo "To check status:"
echo "  sudo systemctl status filebrowser"
echo "  sudo systemctl status caddy"
```

**Step 2: Make it executable**

```bash
chmod +x deploy/install.sh
```

**Step 3: Commit**

```bash
git add -A && git commit -m "feat: idempotent install script with Tailscale FQDN detection"
```

---

## Final Verification

**Run the full test suite one last time:**

```bash
cd /Users/robotdad/Source/filebrowser
python -m pytest tests/ -v
```

All tests across `test_config.py`, `test_filesystem.py`, `test_auth.py`, and `test_files.py` should pass.

**Run the server for manual end-to-end verification:**

```bash
uvicorn filebrowser.main:app --reload
```

Visit `http://127.0.0.1:8000` and verify:
1. Login form appears
2. Valid Linux credentials authenticate successfully
3. File tree loads with home directory contents
4. Clicking folders expands/collapses them
5. Clicking files shows appropriate preview (text, code, images, etc.)
6. Breadcrumb navigation works
7. Upload, new folder, rename, and delete all work
8. Logout returns to login screen
9. Resize to mobile width — sidebar becomes a drawer

**Final commit:**

```bash
git add -A && git commit -m "chore: final cleanup"
```
