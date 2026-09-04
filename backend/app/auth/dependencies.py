from dataclasses import dataclass
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from app.auth.csrf import CsrfValidationError, validate_csrf_request
from app.auth.schemas import AuthErrorCode, AuthErrorDetail
from app.auth.sessions import InvalidSessionError, resolve_session
from app.core.config import Settings, get_settings
from app.db.session import get_db_session

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Minimal active-user boundary exposed to protected route handlers."""

    id: UUID
    is_active: bool


def get_optional_current_user(
    request: Request,
    db: Annotated[DbSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser | None:
    """Resolve the configured session cookie, or return None when it is absent."""

    raw_token = request.cookies.get(settings.effective_session_cookie_name)
    if raw_token is None:
        return None

    try:
        resolved = resolve_session(db, raw_token, settings=settings)
    except InvalidSessionError:
        db.rollback()
        _raise_authentication_required()

    if not resolved.user.is_active:
        db.rollback()
        _raise_authentication_required()

    current_user = AuthenticatedUser(
        id=resolved.user.id,
        is_active=True,
    )
    db.commit()
    return current_user


async def require_current_user(
    current_user: Annotated[
        AuthenticatedUser | None,
        Depends(get_optional_current_user),
    ],
) -> AuthenticatedUser:
    """Require an active TrackSea user resolved from the session cookie."""

    if current_user is None:
        _raise_authentication_required()
    return current_user


async def require_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Protect unsafe cookie-capable requests with CSRF and origin checks."""

    if request.method not in UNSAFE_METHODS:
        return

    try:
        validate_csrf_request(
            cookie_token=request.cookies.get(settings.effective_csrf_cookie_name),
            header_token=request.headers.get(settings.csrf_header_name),
            origin=request.headers.get("origin"),
            referer=request.headers.get("referer"),
            session_token=request.cookies.get(settings.effective_session_cookie_name),
            settings=settings,
        )
    except CsrfValidationError:
        detail = AuthErrorDetail(
            code=AuthErrorCode.CSRF_FAILED,
            message="Request could not be verified.",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.model_dump(mode="json"),
        ) from None


def _raise_authentication_required() -> NoReturn:
    detail = AuthErrorDetail(
        code=AuthErrorCode.AUTHENTICATION_REQUIRED,
        message="Authentication is required.",
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail.model_dump(mode="json"),
    )
