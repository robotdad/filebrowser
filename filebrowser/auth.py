import logging
from dataclasses import dataclass

import pam
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from fastapi import Request, HTTPException
from filebrowser.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AuthenticatedUser:
    """Result of authentication resolution — username is None when unauthenticated."""

    username: str | None


def authenticate_pam(username: str, password: str) -> bool:
    p = pam.pam()
    result = p.authenticate(username, password)
    if result:
        logger.debug("PAM auth succeeded: user=%s", username)
    else:
        logger.warning("PAM auth failed: user=%s", username)
    return result


def create_session_token(username: str, secret_key: str) -> str:
    signer = TimestampSigner(secret_key)
    return signer.sign(username).decode()


def validate_session_token(token: str, secret_key: str, max_age: int) -> str | None:
    signer = TimestampSigner(secret_key)
    try:
        return signer.unsign(token, max_age=max_age).decode()
    except SignatureExpired:
        logger.debug("Session token expired")
        return None
    except BadSignature:
        logger.warning("Bad session token signature (possible tampering)")
        return None


async def require_auth(request: Request) -> str:
    # Trust X-Authenticated-User header set by Caddy forward_auth (frontdoor integration)
    remote_user = request.headers.get("X-Authenticated-User")
    if remote_user:
        logger.debug("Auth: frontdoor user=%s", remote_user)
        return remote_user

    # Fallback: own session cookie (standalone mode — works without frontdoor)
    token = request.cookies.get("session")
    if not token:
        logger.debug("Auth: no session cookie, checking header")
        logger.warning("Auth rejected: no credentials")
        raise HTTPException(
            status_code=401,
            detail={"error": "Not authenticated", "code": "UNAUTHORIZED"},
        )
    username = validate_session_token(
        token, settings.secret_key, settings.session_timeout
    )
    if not username:
        logger.warning("Auth rejected: invalid session token")
        raise HTTPException(
            status_code=401,
            detail={"error": "Session expired or invalid", "code": "UNAUTHORIZED"},
        )
    return username


def get_auth_source(request: Request) -> str:
    """Returns 'frontdoor' when authenticated via X-Authenticated-User header, 'session' otherwise."""
    remote_user = request.headers.get("X-Authenticated-User")
    return "frontdoor" if remote_user else "session"


def resolve_authenticated_user(headers, cookies) -> AuthenticatedUser:
    """Resolve authenticated user from headers (frontdoor) or cookies (session).

    Unlike require_auth, this does NOT raise HTTPException — returns
    AuthenticatedUser(username=None) when unauthenticated.  Designed for
    WebSocket endpoints where HTTP exceptions are not the right pattern.
    """
    # Trust X-Authenticated-User header set by Caddy forward_auth
    remote_user = headers.get("X-Authenticated-User")
    if remote_user:
        logger.debug("WS auth: header user=%s", remote_user)
        return AuthenticatedUser(username=remote_user)

    # Fallback: session cookie
    token = cookies.get("session")
    if not token:
        logger.debug("WS auth: no credentials")
        return AuthenticatedUser(username=None)
    username = validate_session_token(
        token, settings.secret_key, settings.session_timeout
    )
    if not username:
        logger.warning("WS auth rejected: invalid session token")
    return AuthenticatedUser(username=username)
