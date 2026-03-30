import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from filebrowser.auth import require_auth
from filebrowser.config import settings
from filebrowser.services.locations import LocationsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/locations", tags=["locations"])


def get_locations_service() -> LocationsService:
    return LocationsService(settings.data_dir)


@router.get("")
async def list_locations(
    username: str = Depends(require_auth),
    svc: LocationsService = Depends(get_locations_service),
):
    return svc.list()


class AddLocationRequest(BaseModel):
    path: str
    name: str | None = None


@router.post("")
async def add_location(
    body: AddLocationRequest,
    username: str = Depends(require_auth),
    svc: LocationsService = Depends(get_locations_service),
):
    try:
        entry = svc.add(body.path, body.name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"error": str(exc), "code": "NOT_FOUND"}
        )
    except NotADirectoryError as exc:
        raise HTTPException(
            status_code=400, detail={"error": str(exc), "code": "NOT_DIRECTORY"}
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409, detail={"error": str(exc), "code": "DUPLICATE"}
        )
    logger.info("Location added by user=%s path=%s", username, body.path)
    return entry


@router.delete("/{location_id}")
async def remove_location(
    location_id: int,
    username: str = Depends(require_auth),
    svc: LocationsService = Depends(get_locations_service),
):
    try:
        svc.remove(location_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"error": str(exc), "code": "NOT_FOUND"}
        )
    logger.info("Location removed by user=%s id=%d", username, location_id)
    return {"ok": True}
