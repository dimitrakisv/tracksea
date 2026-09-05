from enum import StrEnum

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from app.users.email import normalize_email
from app.users.service import normalize_display_name


class AuthErrorCode(StrEnum):
    """Stable machine-readable codes for authentication failures."""

    AUTHENTICATION_REQUIRED = "authentication_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_CONFLICT = "account_conflict"
    ACCOUNT_LINK_REQUIRED = "account_link_required"
    CSRF_FAILED = "csrf_failed"
    RATE_LIMITED = "rate_limited"


class AuthErrorDetail(BaseModel):
    """Safe authentication error details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: AuthErrorCode
    message: str


class AuthErrorResponse(BaseModel):
    """Authentication error envelope used by the API boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    detail: AuthErrorDetail


class CsrfResponse(BaseModel):
    """The readable token returned by the CSRF bootstrap endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    csrf_token: str


class RegistrationRequest(BaseModel):
    """Validated email-and-password registration input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    email: str
    password: SecretStr
    display_name: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value).canonical

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_display_name(value)
