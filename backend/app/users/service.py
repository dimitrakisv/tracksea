from app.users.models import User
from app.users.schemas import AuthenticationMethod, UserResponse

MIN_DISPLAY_NAME_LENGTH = 1
MAX_DISPLAY_NAME_LENGTH = 80


class InvalidDisplayNameError(ValueError):
    """Raised when a display name cannot be safely stored."""


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
