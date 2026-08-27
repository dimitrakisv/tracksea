from enum import StrEnum

from pydantic import BaseModel, ConfigDict


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
