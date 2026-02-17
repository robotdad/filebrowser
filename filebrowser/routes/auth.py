from fastapi import APIRouter, Response, HTTPException, Request
from pydantic import BaseModel
from filebrowser.auth import (
    authenticate_pam,
    create_session_token,
    validate_session_token,
)
from filebrowser.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    if not authenticate_pam(body.username, body.password):
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid credentials", "code": "AUTH_FAILED"},
        )
    token = create_session_token(body.username, settings.secret_key)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return {"username": body.username}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "Not authenticated", "code": "UNAUTHORIZED"},
        )
    username = validate_session_token(
        token, settings.secret_key, settings.session_timeout
    )
    if not username:
        raise HTTPException(
            status_code=401,
            detail={"error": "Session expired or invalid", "code": "UNAUTHORIZED"},
        )
    return {"username": username}
