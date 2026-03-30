import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_path_within(relative_path: str, base: Path) -> Path:
    """Validate that *relative_path* resolves to a location inside *base*.

    Returns the resolved Path on success.
    Raises PermissionError when the resolved path escapes *base*.
    """
    resolved = (base / relative_path).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        logger.warning("Path traversal blocked: path=%s base=%s", relative_path, base)
        raise PermissionError(f"Path outside base directory: {relative_path}")
    return resolved


FILE_CATEGORIES = {
    "text": {
        ".txt",
        ".log",
        ".csv",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".toml",
        ".env",
        ".conf",
    },
    "code": {
        ".py",
        ".js",
        ".ts",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        ".java",
        ".sh",
        ".sql",
        ".html",
        ".css",
    },
    "markdown": {".md"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"},
    "audio": {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"},
    "video": {".mp4", ".webm", ".mkv", ".mov", ".avi"},
    "pdf": {".pdf"},
    "graphviz": {".dot", ".gv"},
}

# Well-known filenames that are plain text despite having no extension.
KNOWN_TEXT_FILENAMES: set[str] = {
    "LICENSE",
    "LICENCE",
    "README",
    "CONTRIBUTING",
    "CHANGELOG",
    "CHANGES",
    "NOTICE",
    "AUTHORS",
    "COPYING",
    "INSTALL",
    "NEWS",
    "TODO",
    "PATENTS",
}

# Well-known filenames that are code/config despite having no extension.
KNOWN_CODE_FILENAMES: set[str] = {
    "Makefile",
    "makefile",
    "GNUmakefile",
    "Dockerfile",
    "dockerfile",
    "Vagrantfile",
    "Procfile",
    "Brewfile",
    "Gemfile",
    "Rakefile",
    "Guardfile",
    "Capfile",
    "Justfile",
    "justfile",
    "Containerfile",
    "Snakefile",
}


def is_likely_text(path: Path, sample_size: int = 8192) -> bool:
    """Return True if *path* appears to contain UTF-8 text (no null bytes).

    Reads at most *sample_size* bytes from the beginning of the file and
    applies two cheap heuristics:
    1. No null bytes (\\x00) in the sample — binary files almost always have them.
    2. The sample decodes as valid UTF-8.
    """
    try:
        chunk = path.read_bytes()[:sample_size]
        if not chunk:
            return True  # empty files are trivially "text"
        if b"\x00" in chunk:
            return False
        chunk.decode("utf-8")
        return True
    except (UnicodeDecodeError, OSError):
        return False


class FilesystemService:
    def __init__(self, home_dir: Path, locations: list[dict] | None = None):
        self.home_dir = home_dir.resolve()
        self._locations = {
            loc["id"]: Path(loc["path"]).resolve() for loc in (locations or [])
        }

    def validate_path(self, path: str) -> Path:
        if path.startswith("@ext/"):
            return self._validate_external_path(path)
        cleaned = path.lstrip("/")
        resolved = (self.home_dir / cleaned).resolve()
        try:
            resolved.relative_to(self.home_dir)
        except ValueError:
            logger.warning("Path traversal blocked: path=%s", path)
            raise PermissionError(f"Path outside home directory: {path}")
        return resolved

    def _validate_external_path(self, path: str) -> Path:
        """Validate a path within a registered external location."""
        parts = path.split("/", 2)  # ['@ext', '<id>', 'relative/path']
        if len(parts) < 2:
            raise PermissionError(f"Invalid external path: {path}")
        try:
            loc_id = int(parts[1])
        except ValueError:
            raise PermissionError(f"Invalid location ID in path: {path}")
        root = self._locations.get(loc_id)
        if root is None:
            raise PermissionError(f"Unknown external location: {loc_id}")
        relative = parts[2] if len(parts) > 2 else ""
        resolved = (root / relative).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            logger.warning(
                "External path traversal blocked: path=%s root=%s", path, root
            )
            raise PermissionError(f"Path outside external location: {path}")
        return resolved

    def list_directory(self, path: str = "", show_hidden: bool = False) -> list[dict]:
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        entries = []
        for entry in sorted(
            resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())
        ):
            if not show_hidden and entry.name.startswith("."):
                continue
            stat = entry.stat()
            entries.append(
                {
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        logger.debug("List: path=%s entries=%d", path, len(entries))
        return entries

    def detect_file_type(self, filename: str, resolved_path: Path | None = None) -> str:
        """Categorise a file by extension, well-known name, or content sniffing.

        Detection layers (first match wins):
        1. Extension lookup in FILE_CATEGORIES.
        2. Well-known filename lookup (KNOWN_TEXT_FILENAMES / KNOWN_CODE_FILENAMES).
        3. Content sniffing via is_likely_text() when *resolved_path* is supplied.
        """
        name = Path(filename).name
        ext = Path(filename).suffix.lower()

        # Layer 1 – extension-based (fast path)
        for category, extensions in FILE_CATEGORIES.items():
            if ext in extensions:
                return category

        # Layer 2 – well-known filenames (no extension or unrecognised extension)
        if name in KNOWN_TEXT_FILENAMES:
            return "text"
        if name in KNOWN_CODE_FILENAMES:
            return "code"

        # Layer 3 – content sniffing (only when a real path is available)
        if resolved_path is not None and resolved_path.is_file():
            if is_likely_text(resolved_path):
                return "text"

        return "other"

    def _virtual_path(self, original_path: str, resolved: Path) -> str:
        """Return the virtual path string for a resolved filesystem path."""
        if original_path.startswith("@ext/"):
            return original_path
        try:
            return str(resolved.relative_to(self.home_dir))
        except ValueError:
            return original_path

    def get_info(self, path: str) -> dict:
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        stat = resolved.stat()
        return {
            "name": resolved.name,
            "path": self._virtual_path(path, resolved),
            "type": "directory" if resolved.is_dir() else "file",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "category": self.detect_file_type(resolved.name, resolved)
            if resolved.is_file()
            else None,
        }

    def get_file_path(self, path: str) -> Path:
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        if not resolved.is_file():
            raise IsADirectoryError(f"Not a file: {path}")
        return resolved

    def read_file(self, path: str) -> str:
        file_path = self.get_file_path(path)
        logger.debug("Read: path=%s", path)
        return file_path.read_text()

    def delete(self, path: str) -> None:
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        if resolved == self.home_dir:
            logger.warning("Delete blocked: attempt to delete home directory")
            raise PermissionError("Cannot delete home directory")
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()

    def mkdir(self, path: str) -> Path:
        resolved = self.validate_path(path)
        resolved.mkdir(parents=True, exist_ok=True)
        logger.debug("Mkdir: path=%s", path)
        return resolved

    def rename(self, old_path: str, new_path: str) -> Path:
        old_resolved = self.validate_path(old_path)
        new_resolved = self.validate_path(new_path)
        if not old_resolved.exists():
            raise FileNotFoundError(f"Not found: {old_path}")
        old_resolved.rename(new_resolved)
        logger.debug("Rename: old=%s new=%s", old_path, new_path)
        return new_resolved
