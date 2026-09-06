from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import (
    AuthenticatedUser,
    raise_authentication_required,
    require_csrf,
    require_current_user,
)
from app.auth.schemas import AuthErrorResponse
from app.db.session import get_db_session
from app.users.schemas import ProfileUpdateRequest, UserResponse
from app.users.service import (
    CurrentUserUnavailableError,
    update_current_user_display_name,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.patch(
    "/me",
    response_model=UserResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": AuthErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": AuthErrorResponse},
    },
)
def update_current_user_profile(
    profile: ProfileUpdateRequest,
    response: Response,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
    db: Annotated[DbSession, Depends(get_db_session)],
) -> UserResponse:
    try:
        updated = update_current_user_display_name(
            db,
            current_user.id,
            profile.display_name,
        )
    except CurrentUserUnavailableError:
        raise_authentication_required()
    response.headers["Cache-Control"] = "no-store"
    return updated
