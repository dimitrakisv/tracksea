from typing import Protocol
from uuid import UUID


class AuthenticatedUser(Protocol):
    """Minimum user contract exposed by authentication dependencies."""

    id: UUID
    is_active: bool
