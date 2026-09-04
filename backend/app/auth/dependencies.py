from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from app.auth.csrf import CsrfValidationError, validate_csrf_request
from app.auth.schemas import AuthErrorCode, AuthErrorDetail
from app.core.config import Settings, get_settings

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuthenticatedUser(Protocol):
    """Minimum user contract exposed by authentication dependencies."""

    id: UUID
    is_active: bool


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
