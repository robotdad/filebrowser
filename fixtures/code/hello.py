"""
hello.py — Python fixture for CodeMirror syntax highlighting test.
Exercises: class, type hints, dataclass, docstring, function, f-string, list comp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class FileEntry:
    """Represents a single entry in a directory listing."""

    name: str
    path: Path
    size: int
    is_directory: bool
    children: list[FileEntry] = field(default_factory=list)

    @property
    def extension(self) -> str:
        """Return the lowercase file extension, or '' for directories."""
        return "" if self.is_directory else self.path.suffix.lower()

    def human_size(self) -> str:
        """Format size as a human-readable string."""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if self.size < 1024:
                return f"{self.size:.1f} {unit}"
            self.size /= 1024
        return f"{self.size:.1f} PB"

    def __repr__(self) -> str:
        kind = "DIR" if self.is_directory else "FILE"
        return f"<FileEntry [{kind}] {self.path}>"


def find_by_extension(
    root: FileEntry,
    ext: str,
    max_depth: Optional[int] = None,
    _depth: int = 0,
) -> list[FileEntry]:
    """Recursively collect all entries matching the given extension.

    Args:
        root: The root FileEntry to search from.
        ext: Extension to filter on (e.g. '.py').
        max_depth: Stop recursing beyond this depth. None = unlimited.

    Returns:
        A flat list of matching FileEntry objects.
    """
    if max_depth is not None and _depth > max_depth:
        return []

    results = [e for e in root.children if e.extension == ext.lower()]
    for child in root.children:
        if child.is_directory:
            results.extend(find_by_extension(child, ext, max_depth, _depth + 1))
    return results


if __name__ == "__main__":
    demo = FileEntry(
        name="fixtures",
        path=Path("/fixtures"),
        size=0,
        is_directory=True,
        children=[
            FileEntry("hello.py", Path("/fixtures/code/hello.py"), 1024, False),
            FileEntry("app.js", Path("/fixtures/code/app.js"), 2048, False),
        ],
    )
    py_files = find_by_extension(demo, ".py")
    print(f"Found {len(py_files)} Python file(s):")
    for f in py_files:
        print(f"  {f.path} ({f.human_size()})")
