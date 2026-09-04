from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.auth.csrf import issue_csrf_token, set_csrf_cookie
from app.auth.schemas import CsrfResponse
from app.core.config import Settings, get_settings

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
