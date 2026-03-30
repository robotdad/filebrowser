import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_INITIAL_STATE: dict = {"next_id": 1, "locations": []}


class LocationsService:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._store = data_dir / "locations.json"

    def _load(self) -> dict:
        if not self._store.exists():
            return {"next_id": 1, "locations": []}
        try:
            return json.loads(self._store.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted locations.json – resetting")
            return {"next_id": 1, "locations": []}

    def _save(self, state: dict) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._store.write_text(json.dumps(state, indent=2), encoding="utf-8")

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
