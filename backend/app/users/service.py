from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app.users.models import User
from app.users.schemas import AuthenticationMethod, UserResponse

MIN_DISPLAY_NAME_LENGTH = 1
MAX_DISPLAY_NAME_LENGTH = 80


class InvalidDisplayNameError(ValueError):
    """Raised when a display name cannot be safely stored."""


class CurrentUserUnavailableError(Exception):
    """Raised when an active persisted current user is no longer available."""


def normalize_display_name(value: str) -> str:
    """Trim surrounding whitespace and enforce the persisted length boundary."""

    normalized = value.strip()
    if len(normalized) < MIN_DISPLAY_NAME_LENGTH:
        raise InvalidDisplayNameError("Display name is required.")
    if len(normalized) > MAX_DISPLAY_NAME_LENGTH:
        raise InvalidDisplayNameError(
            f"Display name must contain at most {MAX_DISPLAY_NAME_LENGTH} characters."
        )
    return normalized


def build_user_response(user: User) -> UserResponse:
    """Build the safe account representation from persisted authentication state."""

    methods: list[AuthenticationMethod] = []
    if user.password_hash is not None:
        methods.append(AuthenticationMethod.PASSWORD)
    if any(identity.provider == "google" for identity in user.external_identities):
        methods.append(AuthenticationMethod.GOOGLE)

    return UserResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        display_name=user.display_name,
        authentication_methods=tuple(methods),
    )


def get_current_user_profile(db: DbSession, user_id: UUID) -> UserResponse:
    """Load one active current user and return only the safe API boundary."""

    user = _load_current_user(db, user_id)
    return build_user_response(user)


def update_current_user_display_name(
    db: DbSession,
    user_id: UUID,
    display_name: str,
) -> UserResponse:
    """Update only the active current user's normalized display name."""

    normalized_display_name = normalize_display_name(display_name)
    try:
        user = _load_current_user(db, user_id, for_update=True)
        user.display_name = normalized_display_name
        db.flush()
        response = build_user_response(user)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return response


def _load_current_user(
    db: DbSession,
    user_id: UUID,
    *,
    for_update: bool = False,
) -> User:
    statement = (
        select(User)
        .options(selectinload(User.external_identities))
        .where(User.id == user_id, User.is_active.is_(True))
    )
    if for_update:
        statement = statement.with_for_update()
    user = db.scalar(statement)
    if user is None:
        raise CurrentUserUnavailableError("Current user is unavailable.")
    return user
