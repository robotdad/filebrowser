from fastapi import APIRouter, Response, HTTPException, Request, Depends
from pydantic import BaseModel
from filebrowser.auth import (
    authenticate_pam,
    create_session_token,
    require_auth,
    get_auth_source,
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
        secure=settings.secure_cookies,
        samesite="strict",
        max_age=settings.session_timeout,
    )
    return {
        "username": body.username,
        "terminal_enabled": settings.terminal_enabled,
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    response.delete_cookie("session")
    return {"ok": True, "auth_source": get_auth_source(request)}


@router.get("/me")
async def me(
    request: Request, response: Response, username: str = Depends(require_auth)
):
    # In frontdoor mode, the user authenticates through frontdoor and Caddy
    # passes X-Authenticated-User on HTTP requests.  But WebSocket connections
    # don't get that header, so we issue a filebrowser session cookie here
    # that the WebSocket can use as a fallback.
    if get_auth_source(request) == "frontdoor" and "session" not in request.cookies:
        token = create_session_token(username, settings.secret_key)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            max_age=settings.session_timeout,
        )
    return {
        "username": username,
        "auth_source": get_auth_source(request),
        "terminal_enabled": settings.terminal_enabled,
    }
