from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import ip_address
from math import ceil
from typing import Literal

from sqlalchemy import and_, case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.auth.models import AuthThrottleBucket
from app.core.config import Settings

ThrottleScope = Literal["account", "ip"]
THROTTLE_KEY_VERSION = "v1"
MISSING_CLIENT_ADDRESS = "unavailable"
DEFAULT_CLEANUP_LIMIT = 100


@dataclass(frozen=True, slots=True)
class LoginThrottleKeys:
    account: bytes = field(repr=False)
    ip: bytes = field(repr=False)


class LoginRateLimitedError(Exception):
    """A generic active-throttle result containing only a safe retry delay."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Too many sign-in attempts. Try again later.")


def build_login_throttle_keys(
    normalized_email: str,
    direct_client_host: str | None,
    *,
    settings: Settings,
) -> LoginThrottleKeys:
    """Derive domain-separated account and direct-client HMAC digests."""

    return LoginThrottleKeys(
        account=derive_throttle_key(
            "account",
            normalized_email,
            settings=settings,
        ),
        ip=derive_throttle_key(
            "ip",
            canonicalize_client_address(direct_client_host),
            settings=settings,
        ),
    )


def derive_throttle_key(
    scope: ThrottleScope,
    value: str,
    *,
    settings: Settings,
) -> bytes:
    """Return the binary HMAC-SHA-256 digest persisted for one throttle scope."""

    message = f"{THROTTLE_KEY_VERSION}/{scope}/{value}".encode()
    secret = settings.auth_throttle_secret.get_secret_value().encode("utf-8")
    return hmac.digest(secret, message, sha256)


def canonicalize_client_address(value: str | None) -> str:
    """Canonicalize a direct IP or collapse unavailable/invalid values safely."""

    if value is None:
        return MISSING_CLIENT_ADDRESS
    try:
        return ip_address(value).compressed
    except ValueError:
        return MISSING_CLIENT_ADDRESS


def get_login_retry_after(
    db: DbSession,
    keys: LoginThrottleKeys,
    *,
    now: datetime | None = None,
) -> int | None:
    """Return a conservative delay while either login throttle is blocked."""

    checked_at = _as_utc(now)
    blocked_until_values = db.scalars(
        select(AuthThrottleBucket.blocked_until).where(
            or_(
                and_(
                    AuthThrottleBucket.scope == "account",
                    AuthThrottleBucket.key_hash == keys.account,
                ),
                and_(
                    AuthThrottleBucket.scope == "ip",
                    AuthThrottleBucket.key_hash == keys.ip,
                ),
            ),
            AuthThrottleBucket.blocked_until > checked_at,
        )
    )
    active_blocks = [value for value in blocked_until_values if value is not None]
    if not active_blocks:
        return None
    return max(1, ceil((max(active_blocks) - checked_at).total_seconds()))


def record_login_failure(
    db: DbSession,
    keys: LoginThrottleKeys,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> None:
    """Atomically count one credential failure in both caller-owned buckets."""

    failed_at = _as_utc(now)
    _record_scope_failure(
        db,
        scope="account",
        key_hash=keys.account,
        failure_limit=settings.auth_account_failure_limit,
        settings=settings,
        now=failed_at,
    )
    _record_scope_failure(
        db,
        scope="ip",
        key_hash=keys.ip,
        failure_limit=settings.auth_ip_failure_limit,
        settings=settings,
        now=failed_at,
    )


def reset_account_throttle(db: DbSession, account_key_hash: bytes) -> None:
    """Remove only one account's failure state after successful login."""

    db.execute(
        delete(AuthThrottleBucket).where(
            AuthThrottleBucket.scope == "account",
            AuthThrottleBucket.key_hash == account_key_hash,
        )
    )


def cleanup_expired_throttle_buckets(
    db: DbSession,
    *,
    settings: Settings,
    now: datetime | None = None,
    limit: int = DEFAULT_CLEANUP_LIMIT,
) -> int:
    """Delete a bounded set of expired windows without touching active blocks."""

    if limit <= 0:
        raise ValueError("Cleanup limit must be positive.")
    checked_at = _as_utc(now)
    window_cutoff = checked_at - timedelta(
        seconds=settings.auth_throttle_window_seconds
    )
    stale_ids = (
        select(AuthThrottleBucket.id)
        .where(
            or_(
                and_(
                    AuthThrottleBucket.blocked_until.is_(None),
                    AuthThrottleBucket.window_started_at <= window_cutoff,
                ),
                AuthThrottleBucket.blocked_until <= checked_at,
            )
        )
        .order_by(AuthThrottleBucket.updated_at, AuthThrottleBucket.id)
        .limit(limit)
    )
    deleted_ids = db.scalars(
        delete(AuthThrottleBucket)
        .where(AuthThrottleBucket.id.in_(stale_ids))
        .returning(AuthThrottleBucket.id)
    )
    return len(list(deleted_ids))


def _record_scope_failure(
    db: DbSession,
    *,
    scope: ThrottleScope,
    key_hash: bytes,
    failure_limit: int,
    settings: Settings,
    now: datetime,
) -> None:
    bucket = AuthThrottleBucket.__table__
    window_cutoff = now - timedelta(seconds=settings.auth_throttle_window_seconds)
    block_deadline = now + timedelta(seconds=settings.auth_block_seconds)
    active_block = bucket.c.blocked_until > now
    reset_window = or_(
        bucket.c.window_started_at <= window_cutoff,
        and_(
            bucket.c.blocked_until.is_not(None),
            bucket.c.blocked_until <= now,
        ),
    )
    next_count = case(
        (active_block, bucket.c.failure_count),
        (reset_window, 1),
        else_=bucket.c.failure_count + 1,
    )
    next_blocked_until = case(
        (active_block, bucket.c.blocked_until),
        (reset_window, block_deadline if failure_limit == 1 else None),
        (bucket.c.failure_count + 1 >= failure_limit, block_deadline),
        else_=None,
    )
    next_window_started_at = case(
        (active_block, bucket.c.window_started_at),
        (reset_window, now),
        else_=bucket.c.window_started_at,
    )
    initial_blocked_until = block_deadline if failure_limit == 1 else None

    statement = insert(AuthThrottleBucket).values(
        scope=scope,
        key_hash=key_hash,
        failure_count=1,
        window_started_at=now,
        blocked_until=initial_blocked_until,
        updated_at=now,
    )
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_auth_throttle_buckets_scope_key_hash",
            set_={
                "failure_count": next_count,
                "window_started_at": next_window_started_at,
                "blocked_until": next_blocked_until,
                "updated_at": now,
            },
        )
    )


def _as_utc(value: datetime | None) -> datetime:
    selected = value or datetime.now(UTC)
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError("Throttle timestamps must be timezone-aware.")
    return selected.astimezone(UTC)
