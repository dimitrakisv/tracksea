from starlette.responses import Response

from app.core.config import Settings, get_settings


def set_session_cookie(
    response: Response,
    raw_token: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Set the opaque session token with the centralized cookie policy."""

    selected_settings = settings or get_settings()
    response.set_cookie(
        key=selected_settings.effective_session_cookie_name,
        value=raw_token,
        max_age=selected_settings.session_lifetime_seconds,
        path="/",
        secure=selected_settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(
    response: Response,
    *,
    settings: Settings | None = None,
) -> None:
    """Expire the session cookie using attributes compatible with creation."""

    selected_settings = settings or get_settings()
    response.delete_cookie(
        key=selected_settings.effective_session_cookie_name,
        path="/",
        secure=selected_settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
