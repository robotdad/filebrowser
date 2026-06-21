import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from filebrowser.auth import require_auth
from filebrowser.config import settings
from filebrowser.services.filesystem import FilesystemService
from filebrowser.services.locations import LocationsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


def get_fs() -> FilesystemService:
    locations = LocationsService(settings.data_dir).list()
    return FilesystemService(settings.home_dir, locations=locations)


@router.get("")
async def list_directory(
    path: str = "",
    show_hidden: bool = False,
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        entries = fs.list_directory(path, show_hidden=show_hidden)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "Directory not found", "code": "NOT_FOUND"},
        )
    except NotADirectoryError:
        raise HTTPException(
            status_code=400,
            detail={"error": "Not a directory", "code": "NOT_DIRECTORY"},
        )
    logger.debug("List: user=%s path=%s", username, path)
    return entries


@router.get("/info")
async def file_info(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        info = fs.get_info(path)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"}
        )
    logger.debug("Info: user=%s path=%s", username, path)
    return info


@router.get("/content")
async def get_content(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        file_path = fs.get_file_path(path)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail={"error": "File not found", "code": "NOT_FOUND"}
        )
    except IsADirectoryError:
        raise HTTPException(
            status_code=400, detail={"error": "Is a directory", "code": "IS_DIRECTORY"}
        )
    logger.info("Read: user=%s path=%s", username, path)
    
    # Determine the appropriate media type based on file category
    file_category = fs.detect_file_type(file_path.name, file_path)
    
    # Image files need their actual MIME type for proper browser rendering
    # (especially SVG which requires image/svg+xml to display in <img> tags).
    # Text/code files stay as text/plain to prevent the API client from
    # auto-parsing file content (e.g. .json → application/json would cause
    # the frontend to receive a parsed object instead of raw text).
    if file_category == "image":
        guessed_type, _ = mimetypes.guess_type(str(file_path))
        media_type = guessed_type if guessed_type else "application/octet-stream"
        
        # SVG files can contain JavaScript via <script> tags, creating an XSS
        # vulnerability if served inline without protection. Add security headers
        # to prevent script execution while still allowing inline display.
        if media_type == "image/svg+xml":
            headers = {
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"
            }
            return FileResponse(file_path, media_type=media_type, headers=headers)
    elif file_category == "pdf":
        # PDF files need application/pdf MIME type for proper browser rendering.
        # PDFs can contain JavaScript, creating an XSS vulnerability if served inline.
        # Force download (Content-Disposition: attachment) instead of inline rendering
        # to prevent embedded JavaScript execution. Browser PDF viewers often do NOT
        # honor CSP headers, so attachment disposition is the only reliable mitigation.
        media_type = "application/pdf"
        headers = {
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox"
        }
        # Use FastAPI's filename parameter for RFC 6266 compliant header encoding
        # instead of manual construction to prevent header injection attacks
        return FileResponse(file_path, media_type=media_type, headers=headers, filename=file_path.name)
    else:
        media_type = "text/plain; charset=utf-8"
    
    return FileResponse(file_path, media_type=media_type)


@router.get("/download")
async def download_file(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        file_path = fs.get_file_path(path)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail={"error": "File not found", "code": "NOT_FOUND"}
        )
    except IsADirectoryError:
        raise HTTPException(
            status_code=400, detail={"error": "Is a directory", "code": "IS_DIRECTORY"}
        )
    logger.info("Download: user=%s path=%s", username, path)
    return FileResponse(file_path, filename=file_path.name)


@router.post("/upload")
async def upload_file(
    path: str = "",
    file: UploadFile = File(...),
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        dir_path = fs.validate_path(path)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )

    if not dir_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"error": "Not a directory", "code": "NOT_DIRECTORY"},
        )

    safe_name = Path(file.filename or "").name
    if not safe_name:
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid filename", "code": "INVALID_FILENAME"},
        )

    dest = dir_path / safe_name
    try:
        dest.resolve().relative_to(fs.home_dir)
    except ValueError:
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )

    size = 0
    try:
        with open(dest, "wb") as f:
            while chunk := await file.read(8192):
                size += len(chunk)
                if size > settings.upload_max_size:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail={"error": "File too large", "code": "FILE_TOO_LARGE"},
                    )
                f.write(chunk)
    except OSError as e:
        dest.unlink(missing_ok=True)
        if "No space left" in str(e):
            raise HTTPException(
                status_code=507,
                detail={
                    "error": "Insufficient storage",
                    "code": "INSUFFICIENT_STORAGE",
                },
            )
        raise

    logger.info("Upload: user=%s path=%s/%s size=%d", username, path, safe_name, size)
    return {"name": safe_name, "size": size}


@router.post("/mkdir")
async def make_directory(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        result = fs.mkdir(path)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    logger.info("Mkdir: user=%s path=%s", username, path)
    return {"path": str(result.relative_to(fs.home_dir))}


class WriteContentRequest(BaseModel):
    path: str
    content: str


@router.put("/content")
async def write_content(
    body: WriteContentRequest,
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        file_path = fs.validate_path(body.path)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, body.path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    if not file_path.parent.exists():
        raise HTTPException(
            status_code=404,
            detail={"error": "Parent directory not found", "code": "NOT_FOUND"},
        )
    if file_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"error": "Is a directory", "code": "IS_DIRECTORY"},
        )
    file_path.write_text(body.content, encoding="utf-8")
    logger.info(
        "Write: user=%s path=%s size=%d", username, body.path, file_path.stat().st_size
    )
    return {"ok": True, "size": file_path.stat().st_size}


class RenameRequest(BaseModel):
    old_path: str
    new_path: str


@router.put("/rename")
async def rename_file(
    body: RenameRequest,
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        result = fs.rename(body.old_path, body.new_path)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, body.old_path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"}
        )
    logger.info("Rename: user=%s old=%s new=%s", username, body.old_path, body.new_path)
    return {"path": str(result.relative_to(fs.home_dir))}


@router.delete("")
async def delete_file(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        fs.delete(path)
    except PermissionError:
        logger.warning("Path forbidden: user=%s path=%s", username, path)
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"}
        )
    logger.info("Delete: user=%s path=%s", username, path)
    return {"ok": True}
