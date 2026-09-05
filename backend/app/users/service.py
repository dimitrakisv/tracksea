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
