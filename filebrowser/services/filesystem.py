import shutil
from datetime import datetime
from pathlib import Path

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
}


class FilesystemService:
    def __init__(self, home_dir: Path):
        self.home_dir = home_dir.resolve()

    def validate_path(self, path: str) -> Path:
        cleaned = path.lstrip("/")
        resolved = (self.home_dir / cleaned).resolve()
        try:
            resolved.relative_to(self.home_dir)
        except ValueError:
            raise PermissionError(f"Path outside home directory: {path}")
        return resolved

    def list_directory(self, path: str = "") -> list[dict]:
        resolved = self.validate_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Not found: {path}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        entries = []
        for entry in sorted(
            resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())
        ):
            stat = entry.stat()
            entries.append(
                {
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        return entries

    def detect_file_type(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        for category, extensions in FILE_CATEGORIES.items():
            if ext in extensions:
                return category
        return "other"

    def get_info(self, path: str) -> dict:
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
            "category": self.detect_file_type(resolved.name)
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
        return file_path.read_text()

    def delete(self, path: str) -> None:
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
        resolved = self.validate_path(path)
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def rename(self, old_path: str, new_path: str) -> Path:
        old_resolved = self.validate_path(old_path)
        new_resolved = self.validate_path(new_path)
        if not old_resolved.exists():
            raise FileNotFoundError(f"Not found: {old_path}")
        old_resolved.rename(new_resolved)
        return new_resolved
