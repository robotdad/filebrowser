from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from filebrowser.auth import require_auth
from filebrowser.services.filesystem import FilesystemService
from filebrowser.config import settings

router = APIRouter(prefix="/api/files", tags=["files"])


def get_fs() -> FilesystemService:
    return FilesystemService(settings.home_dir)


@router.get("")
async def list_directory(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        return fs.list_directory(path)
    except PermissionError:
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


@router.get("/info")
async def file_info(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        return fs.get_info(path)
    except PermissionError:
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"}
        )


@router.get("/content")
async def get_content(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        file_path = fs.get_file_path(path)
    except PermissionError:
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
    return FileResponse(file_path)


@router.get("/download")
async def download_file(
    path: str = "",
    username: str = Depends(require_auth),
    fs: FilesystemService = Depends(get_fs),
):
    try:
        file_path = fs.get_file_path(path)
    except PermissionError:
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
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )

    if not dir_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"error": "Not a directory", "code": "NOT_DIRECTORY"},
        )

    safe_name = Path(file.filename).name
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
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    return {"path": str(result.relative_to(fs.home_dir))}


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
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"}
        )
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
        raise HTTPException(
            status_code=403, detail={"error": "Access denied", "code": "PATH_FORBIDDEN"}
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail={"error": "Not found", "code": "NOT_FOUND"}
        )
    return {"ok": True}
