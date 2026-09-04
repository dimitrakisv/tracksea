import base64
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from app.auth.models import Session
from app.core.config import Settings, get_settings
from app.users.models import User

SESSION_RANDOM_BYTES = 32


class InvalidSessionError(Exception):
    """A generic invalid-session failure that does not reveal its cause."""


@dataclass(frozen=True, slots=True)
class CreatedSession:
    session_id: UUID
    raw_token: str = field(repr=False)
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    session_id: UUID
    user: User
    expires_at: datetime


def generate_session_token() -> str:
    """Create an unpadded URL-safe token from 256 bits of randomness."""

    random_bytes = secrets.token_bytes(SESSION_RANDOM_BYTES)
    return base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode("ascii")


def hash_session_token(raw_token: str) -> bytes:
    """Return the binary SHA-256 digest used for database lookup."""

    return sha256(raw_token.encode("utf-8")).digest()


def create_session(
    db: DbSession,
    user_id: UUID,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> CreatedSession:
    """Add a new session to the caller-owned transaction and return its raw token."""

    selected_settings = settings or get_settings()
    created_at = _as_utc(now)
    raw_token = generate_session_token()
    expires_at = created_at + timedelta(
        seconds=selected_settings.session_lifetime_seconds
    )
    record = Session(
        user_id=user_id,
        token_hash=hash_session_token(raw_token),
        created_at=created_at,
        expires_at=expires_at,
    )
    db.add(record)
    db.flush()
    return CreatedSession(
        session_id=record.id,
        raw_token=raw_token,
        created_at=created_at,
        expires_at=expires_at,
    )


def resolve_session(
    db: DbSession,
    raw_token: str,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ResolvedSession:
    """Resolve an active digest-backed session inside the caller's transaction."""

    selected_settings = settings or get_settings()
    resolved_at = _as_utc(now)
    record = db.scalar(
        select(Session)
        .options(joinedload(Session.user))
        .where(Session.token_hash == hash_session_token(raw_token))
    )
    if (
        record is None
        or record.revoked_at is not None
        or record.expires_at <= resolved_at
    ):
        raise InvalidSessionError("Session is not active.")

    last_seen_cutoff = resolved_at - timedelta(
        seconds=selected_settings.session_last_seen_interval_seconds
    )
    if record.last_seen_at is None or record.last_seen_at <= last_seen_cutoff:
        record.last_seen_at = resolved_at
        db.flush()

    return ResolvedSession(
        session_id=record.id,
        user=record.user,
        expires_at=record.expires_at,
    )


def revoke_session(
    db: DbSession,
    session_id: UUID,
    *,
    now: datetime | None = None,
) -> bool:
    """Mark one session revoked without committing or deleting its row."""

    record = db.get(Session, session_id)
    if record is None:
        return False
    if record.revoked_at is None:
        record.revoked_at = _as_utc(now)
        db.flush()
    return True


def _as_utc(value: datetime | None) -> datetime:
    selected = value or datetime.now(UTC)
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError("Session timestamps must be timezone-aware.")
    return selected.astimezone(UTC)
