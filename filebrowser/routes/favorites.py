import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from filebrowser.auth import require_auth
from filebrowser.config import settings
from filebrowser.services.favorites import FavoritesService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


def get_favorites_service() -> FavoritesService:
    return FavoritesService(settings.data_dir)


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
