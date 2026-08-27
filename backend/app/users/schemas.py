from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
