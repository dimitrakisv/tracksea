from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class AuthenticationMethod(StrEnum):
    """Authentication methods safe to expose for the current user."""

    PASSWORD = "password"
    GOOGLE = "google"


class UserResponse(BaseModel):
    """Public account data returned to an authenticated user."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    email: str
    email_verified: bool
    display_name: str
    authentication_methods: tuple[AuthenticationMethod, ...]


class ProfileUpdateRequest(BaseModel):
    """The only profile field writable during Sprint 2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        from app.users.service import normalize_display_name

        return normalize_display_name(value)
