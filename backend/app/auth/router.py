from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from app.auth.cookies import clear_session_cookie, set_session_cookie
from app.auth.csrf import issue_csrf_token, set_csrf_cookie
from app.auth.dependencies import require_csrf
from app.auth.passwords import PasswordPolicyError
from app.auth.schemas import (
    AuthErrorCode,
    AuthErrorDetail,
    AuthErrorResponse,
    CsrfResponse,
    LoginRequest,
    RegistrationRequest,
)
from app.auth.service import (
    AccountConflictError,
    InvalidCredentialsError,
    login_user,
    logout_session,
    register_user,
)
from app.auth.throttling import LoginRateLimitedError
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.users.schemas import UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/csrf", response_model=CsrfResponse)
async def read_csrf(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CsrfResponse:
    session_token = request.cookies.get(settings.effective_session_cookie_name)
    token = issue_csrf_token(settings=settings, session_token=session_token)
    set_csrf_cookie(response, token, settings=settings)
    response.headers["Cache-Control"] = "no-store"
    return CsrfResponse(csrf_token=token)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    responses={status.HTTP_409_CONFLICT: {"model": AuthErrorResponse}},
)
def register(
    registration: RegistrationRequest,
    response: Response,
    db: Annotated[DbSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    try:
        result = register_user(db, registration, settings=settings)
    except PasswordPolicyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": error.code.value, "message": str(error)},
        ) from None
    except AccountConflictError:
        detail = AuthErrorDetail(
            code=AuthErrorCode.ACCOUNT_CONFLICT,
            message="An account cannot be created with these details.",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail.model_dump(mode="json"),
        ) from None

    _set_authenticated_cookies(
        response,
        result.raw_session_token,
        settings=settings,
    )
    response.headers["Cache-Control"] = "no-store"
    return result.user


@router.post(
    "/login",
    response_model=UserResponse,
    dependencies=[Depends(require_csrf)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": AuthErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": AuthErrorResponse},
    },
)
def login(
    login_request: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[DbSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    try:
        direct_client_host = request.client.host if request.client is not None else None
        result = login_user(
            db,
            login_request,
            settings=settings,
            direct_client_host=direct_client_host,
        )
    except LoginRateLimitedError as error:
        detail = AuthErrorDetail(
            code=AuthErrorCode.RATE_LIMITED,
            message="Too many sign-in attempts. Try again later.",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail.model_dump(mode="json"),
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from None
    except InvalidCredentialsError:
        detail = AuthErrorDetail(
            code=AuthErrorCode.INVALID_CREDENTIALS,
            message="Email or password is incorrect.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail.model_dump(mode="json"),
        ) from None

    _set_authenticated_cookies(
        response,
        result.raw_session_token,
        settings=settings,
    )
    response.headers["Cache-Control"] = "no-store"
    return result.user


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def logout(
    request: Request,
    response: Response,
    db: Annotated[DbSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    raw_session_token = request.cookies.get(settings.effective_session_cookie_name)
    logout_session(db, raw_session_token, settings=settings)

    clear_session_cookie(response, settings=settings)
    anonymous_csrf = issue_csrf_token(settings=settings)
    set_csrf_cookie(response, anonymous_csrf, settings=settings)
    response.headers["Cache-Control"] = "no-store"


def _set_authenticated_cookies(
    response: Response,
    raw_session_token: str,
    *,
    settings: Settings,
) -> None:
    set_session_cookie(response, raw_session_token, settings=settings)
    csrf_token = issue_csrf_token(
        settings=settings,
        session_token=raw_session_token,
    )
    set_csrf_cookie(response, csrf_token, settings=settings)
