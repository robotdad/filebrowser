from pathlib import Path


class FilesystemService:
    def __init__(self, root: Path) -> None:
        self.root = root
