import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from filebrowser.auth import require_auth
from filebrowser.config import settings
from filebrowser.services.favorites import FavoritesService
from filebrowser.services.locations import LocationsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


def get_favorites_service() -> FavoritesService:
    return FavoritesService(settings.data_dir)


def _validate_favorite_path(raw_path: str) -> Path:
    """Validate *raw_path* for use as a favorite directory.

    Raises ``HTTPException`` (4xx) for every invalid input:

    - Empty string or whitespace-only → 400 EMPTY_PATH
    - Resolves to a path that does not exist → 400 NOT_FOUND
    - Resolves to a path that is not a directory → 400 NOT_DIRECTORY
    - Resolves to a path outside ``home_dir`` *and* outside every
      registered location → 403 PATH_FORBIDDEN

    Returns the resolved ``Path`` on success.
    """
    if not raw_path or not raw_path.strip():
        raise HTTPException(
            status_code=400,
            detail={"error": "Path must not be empty", "code": "EMPTY_PATH"},
        )

    resolved = Path(raw_path).resolve()

    if not resolved.exists():
        raise HTTPException(
            status_code=400,
            detail={"error": f"Path does not exist: {raw_path}", "code": "NOT_FOUND"},
        )

    if not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Path is not a directory: {raw_path}",
                "code": "NOT_DIRECTORY",
            },
        )

    # Containment check: the resolved path must be inside home_dir OR
    # inside at least one registered external location.
    home = settings.home_dir.resolve()
    try:
        resolved.relative_to(home)
        return resolved  # inside home_dir -- allowed
    except ValueError:
        pass

    # Check registered external locations.
    locations = LocationsService(settings.data_dir).list()
    for loc in locations:
        loc_root = Path(loc["path"]).resolve()
        try:
            resolved.relative_to(loc_root)
            return resolved  # inside a registered location -- allowed
        except ValueError:
            continue

    logger.warning(
        "Favorite path blocked (outside all permitted roots): path=%s", raw_path
    )
    raise HTTPException(
        status_code=403,
        detail={
            "error": f"Path outside permitted roots: {raw_path}",
            "code": "PATH_FORBIDDEN",
        },
    )


@router.get("")
async def list_favorites(
    username: str = Depends(require_auth),
    svc: FavoritesService = Depends(get_favorites_service),
):
    return svc.list()


class AddFavoriteRequest(BaseModel):
    path: str


@router.post("")
async def add_favorite(
    body: AddFavoriteRequest,
    username: str = Depends(require_auth),
    svc: FavoritesService = Depends(get_favorites_service),
):
    _validate_favorite_path(body.path)
    entry = svc.add(body.path)
    logger.info("Favorite added by user=%s path=%s", username, body.path)
    return entry


@router.delete("")
async def remove_favorite(
    request: Request,
    path: str | None = None,
    username: str = Depends(require_auth),
    svc: FavoritesService = Depends(get_favorites_service),
):
    # Path value may arrive as a query-string parameter OR as a JSON
    # request body field -- favorites are identified by path, never by a
    # numeric id, and the criteria explicitly allow either request shape.
    if not path:
        try:
            body = await request.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            path = body.get("path")

    if not path:
        raise HTTPException(
            status_code=400,
            detail={"error": "Missing path value", "code": "MISSING_PATH"},
        )

    try:
        svc.remove(path)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"error": str(exc), "code": "NOT_FOUND"}
        )
    logger.info("Favorite removed by user=%s path=%s", username, path)
    return {"ok": True}
