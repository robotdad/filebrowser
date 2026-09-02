import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FavoritesService:
    """On-disk store for pinned favorite folders.

    Mirrors the persistence pattern of the sibling ``LocationsService``
    (data_dir-scoped JSON file, ``Path(...).resolve()`` for equality) but
    deliberately diverges on two points that the acceptance criteria call
    out as favorites-specific:

    - Entries are identified by their **resolved path value**, never by a
      numeric id (``remove`` takes a path, not an id).
    - ``add`` is idempotent: adding an already-present (resolved-equal)
      path returns the existing entry rather than raising. This is an
      intentional asymmetry with ``LocationsService.add``, which raises
      ``ValueError`` on duplicates -- favorites must not error on a
      repeated "pin" action.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._store = data_dir / "favorites.json"

    def _load(self) -> dict:
        if not self._store.exists():
            return {"favorites": []}
        try:
            return json.loads(self._store.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted favorites.json \u2013 resetting")
            return {"favorites": []}

    def _save(self, state: dict) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._store.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def list(self) -> list[dict]:
        return self._load()["favorites"]

    def add(self, path: str) -> dict:
        """Add a favorite by path.

        Idempotent: if a resolved-equal path is already stored, the
        existing entry is returned and no duplicate is created (per the
        resolved/canonicalized path-equality rule that
        ``LocationsService`` also uses).
        """
        resolved = Path(path).resolve()
        state = self._load()

        for fav in state["favorites"]:
            if Path(fav["path"]).resolve() == resolved:
                return fav

        entry: dict = {"path": str(resolved)}
        state["favorites"].append(entry)
        self._save(state)
        logger.info("Favorite added: path=%s", resolved)
        return entry

    def remove(self, path: str) -> None:
        """Remove a favorite identified by its (resolved) path value."""
        resolved = Path(path).resolve()
        state = self._load()
        before = len(state["favorites"])
        state["favorites"] = [
            fav for fav in state["favorites"] if Path(fav["path"]).resolve() != resolved
        ]
        if len(state["favorites"]) == before:
            raise KeyError(f"Favorite not found: {path}")
        self._save(state)
        logger.info("Favorite removed: path=%s", resolved)
