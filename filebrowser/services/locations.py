import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_INITIAL_STATE: dict = {"next_id": 1, "locations": []}


class LocationsService:
    """On-disk store for registered external locations.

    Write durability
    ~~~~~~~~~~~~~~~~
    ``_save`` uses a write-to-temp-then-rename pattern (atomic on POSIX).
    An interrupted write therefore leaves the previously committed file
    intact; the partial temp file is simply abandoned.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._store = data_dir / "locations.json"

    def _load(self) -> dict:
        if not self._store.exists():
            return {"next_id": 1, "locations": []}
        try:
            return json.loads(self._store.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted locations.json \u2013 resetting")
            return {"next_id": 1, "locations": []}

    def _save(self, state: dict) -> None:
        """Write *state* atomically using a temp-file-then-rename strategy.

        On POSIX systems ``os.replace`` is atomic within the same
        filesystem, so a reader always sees either the old complete file or
        the new complete file -- never a partial write.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # Write to a sibling temp file in the same directory so that
        # os.replace stays on the same filesystem (required for atomicity).
        fd, tmp_path = tempfile.mkstemp(
            dir=self._data_dir, prefix=".locations_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(state, indent=2))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self._store)
        except Exception:
            # Best-effort cleanup of the temp file on failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def list(self) -> list[dict]:
        return self._load()["locations"]

    def get(self, location_id: int) -> dict | None:
        for loc in self._load()["locations"]:
            if loc["id"] == location_id:
                return loc
        return None

    def add(self, path: str, name: str | None = None) -> dict:
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        state = self._load()

        # Deduplicate by resolved path
        for loc in state["locations"]:
            if Path(loc["path"]).resolve() == resolved:
                raise ValueError(f"Location already registered: {path}")

        loc_id = state["next_id"]
        display_name = name or resolved.name or str(resolved)
        entry: dict = {"id": loc_id, "path": str(resolved), "name": display_name}
        state["locations"].append(entry)
        state["next_id"] = loc_id + 1
        self._save(state)
        logger.info(
            "Location added: id=%d path=%s name=%s", loc_id, resolved, display_name
        )
        return entry

    def remove(self, location_id: int) -> None:
        state = self._load()
        before = len(state["locations"])
        state["locations"] = [loc for loc in state["locations"] if loc["id"] != location_id]
        if len(state["locations"]) == before:
            raise KeyError(f"Location not found: {location_id}")
        self._save(state)
        logger.info("Location removed: id=%d", location_id)
