from enum import StrEnum
from functools import cache
from pathlib import Path
from unicodedata import normalize

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 128

_PASSWORD_HASH = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "xijg9HrpQW5vGEvyzTLmrA$Cxrhu6SvR9nRtGRPG6Kd0BWq2kbjTeOvaKMWPSQ6sxA"
)
_COMMON_PASSWORD_PATH = Path(__file__).with_name("data") / "common-passwords.txt"
_TRACKSEA_SPECIFIC_PASSWORDS = frozenset(
    {
        "tracksea-password",
        "tracksea1234567",
        "trackseatracksea",
    }
)


class PasswordPolicyCode(StrEnum):
    """Stable policy failures suitable for a future registration boundary."""

    TOO_SHORT = "password_too_short"
    TOO_LONG = "password_too_long"
    COMMON = "password_too_common"


class PasswordPolicyError(ValueError):
    """A safe password-policy failure that never includes the candidate."""

    def __init__(self, code: PasswordPolicyCode, message: str) -> None:
        self.code = code
        super().__init__(message)


def normalize_password(password: str) -> str:
    """Apply NFC only; whitespace and case remain unchanged."""

    return normalize("NFC", password)


@cache
def _common_passwords() -> frozenset[str]:
    return frozenset(
        normalize_password(password)
        for password in _COMMON_PASSWORD_PATH.read_text(encoding="utf-8").splitlines()
        if password
    )


def validate_password(password: str) -> str:
    """Return the normalized candidate when it satisfies the new-password policy."""

    normalized = normalize_password(password)
    if len(normalized) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            PasswordPolicyCode.TOO_SHORT,
            f"Password must contain at least {MIN_PASSWORD_LENGTH} characters.",
        )
    if len(normalized) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            PasswordPolicyCode.TOO_LONG,
            f"Password must contain at most {MAX_PASSWORD_LENGTH} characters.",
        )
    if (
        normalized in _common_passwords()
        or normalized.casefold() in _TRACKSEA_SPECIFIC_PASSWORDS
    ):
        raise PasswordPolicyError(
            PasswordPolicyCode.COMMON,
            "Choose a less common password.",
        )
    return normalized


def hash_password(password: str) -> str:
    """Validate and hash a new password with the recommended Argon2id hasher."""

    return _PASSWORD_HASH.hash(validate_password(password))


def verify_password(password: str, password_hash: str) -> bool:
    """Verify an existing password without reapplying new-password policy."""

    try:
        return _PASSWORD_HASH.verify(normalize_password(password), password_hash)
    except UnknownHashError:
        return False


def verify_and_update_password(
    password: str,
    password_hash: str,
) -> tuple[bool, str | None]:
    """Verify a password and return a replacement hash when parameters are stale."""

    try:
        return _PASSWORD_HASH.verify_and_update(
            normalize_password(password),
            password_hash,
        )
    except UnknownHashError:
        return False, None


def verify_dummy_password(password: str) -> bool:
    """Perform a real Argon2id verification without a user credential."""

    return verify_password(password, _DUMMY_PASSWORD_HASH)
