import json
import logging
import os
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level lock registry so every FavoritesService that shares the same
# data_dir path shares the same in-process lock.
_lock_registry: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _get_lock(store_path: str) -> threading.Lock:
    with _registry_lock:
        if store_path not in _lock_registry:
            _lock_registry[store_path] = threading.Lock()
        return _lock_registry[store_path]


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

    Write durability
    ~~~~~~~~~~~~~~~~
    ``_save`` uses a write-to-temp-then-rename pattern (atomic on POSIX).
    An interrupted write therefore leaves the previously committed file
    intact; the partial temp file is simply abandoned.

    Concurrency safety
    ~~~~~~~~~~~~~~~~~~
    A per-store ``threading.Lock`` serialises all load-mutate-save cycles
    so that concurrent add/remove calls from different threads do not race.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._store = data_dir / "favorites.json"
        self._lock = _get_lock(str(self._store.resolve()))

    def _load(self) -> dict:
        if not self._store.exists():
            return {"favorites": []}
        try:
            return json.loads(self._store.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted favorites.json \u2013 resetting")
            return {"favorites": []}

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
            dir=self._data_dir, prefix=".favorites_", suffix=".tmp"
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
        return self._load()["favorites"]

    def add(self, path: str) -> dict:
        """Add a favorite by path.

        Idempotent: if a resolved-equal path is already stored, the
        existing entry is returned and no duplicate is created (per the
        resolved/canonicalized path-equality rule that
        ``LocationsService`` also uses).

        The load-mutate-save cycle is protected by ``self._lock`` so that
        concurrent callers cannot interleave their writes.
        """
        resolved = Path(path).resolve()
        with self._lock:
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
        with self._lock:
            state = self._load()
            before = len(state["favorites"])
            state["favorites"] = [
                fav
                for fav in state["favorites"]
                if Path(fav["path"]).resolve() != resolved
            ]
            if len(state["favorites"]) == before:
                raise KeyError(f"Favorite not found: {path}")
            self._save(state)
        logger.info("Favorite removed: path=%s", resolved)
