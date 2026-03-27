import pam
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from fastapi import Request, HTTPException
from filebrowser.config import settings


def authenticate_pam(username: str, password: str) -> bool:
    p = pam.pam()
    return p.authenticate(username, password)


def create_session_token(username: str, secret_key: str) -> str:
    signer = TimestampSigner(secret_key)
    return signer.sign(username).decode()


def validate_session_token(token: str, secret_key: str, max_age: int) -> str | None:
    signer = TimestampSigner(secret_key)
    try:
        return signer.unsign(token, max_age=max_age).decode()
    except (BadSignature, SignatureExpired):
        return None


async def require_auth(request: Request) -> str:
    # Trust X-Authenticated-User header set by Caddy forward_auth (frontdoor integration)
    remote_user = request.headers.get("X-Authenticated-User")
    if remote_user:
        return remote_user

    # Fallback: own session cookie (standalone mode — works without frontdoor)
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "Not authenticated", "code": "UNAUTHORIZED"},
        )
    username = validate_session_token(token, settings.secret_key, settings.session_timeout)
    if not username:
        raise HTTPException(
            status_code=401,
            detail={"error": "Session expired or invalid", "code": "UNAUTHORIZED"},
        )
    return username


def get_auth_source(request: Request) -> str:
    """Returns 'frontdoor' when authenticated via X-Authenticated-User header, 'session' otherwise."""
    remote_user = request.headers.get("X-Authenticated-User")
    return "frontdoor" if remote_user else "session"
