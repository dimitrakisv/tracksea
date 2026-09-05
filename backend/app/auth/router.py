from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from app.auth.cookies import set_session_cookie
from app.auth.csrf import issue_csrf_token, set_csrf_cookie
from app.auth.dependencies import require_csrf
from app.auth.passwords import PasswordPolicyError
from app.auth.schemas import (
    AuthErrorCode,
    AuthErrorDetail,
    AuthErrorResponse,
    CsrfResponse,
    RegistrationRequest,
)
from app.auth.service import AccountConflictError, register_user
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

    set_session_cookie(response, result.raw_session_token, settings=settings)
    csrf_token = issue_csrf_token(
        settings=settings,
        session_token=result.raw_session_token,
    )
    set_csrf_cookie(response, csrf_token, settings=settings)
    response.headers["Cache-Control"] = "no-store"
    return result.user
