from dataclasses import dataclass, field
from datetime import datetime

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app.auth.passwords import (
    hash_password,
    verify_and_update_password,
    verify_dummy_password,
)
from app.auth.schemas import LoginRequest, RegistrationRequest
from app.auth.sessions import (
    InvalidSessionError,
    create_session,
    resolve_session,
    revoke_session,
)
from app.auth.throttling import (
    LoginRateLimitedError,
    build_login_throttle_keys,
    cleanup_expired_throttle_buckets,
    get_login_retry_after,
    record_login_failure,
    reset_account_throttle,
)
from app.core.config import Settings
from app.users.email import normalize_email
from app.users.models import User
from app.users.schemas import UserResponse
from app.users.service import build_user_response, normalize_display_name

NORMALIZED_EMAIL_CONSTRAINT = "uq_users_normalized_email"


class AccountConflictError(Exception):
    """A generic registration conflict that reveals no account details."""


class InvalidCredentialsError(Exception):
    """A generic password-authentication failure safe for the HTTP boundary."""


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user: UserResponse
    raw_session_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: UserResponse
    raw_session_token: str = field(repr=False)


def register_user(
    db: DbSession,
    registration: RegistrationRequest,
    *,
    settings: Settings,
) -> RegistrationResult:
    """Create a password user and initial session in one committed transaction."""

    email = normalize_email(registration.email)
    display_name = normalize_display_name(registration.display_name)
    password_hash = hash_password(registration.password.get_secret_value())
    user = User(
        email=email.canonical,
        normalized_email=email.normalized,
        display_name=display_name,
        password_hash=password_hash,
        email_verified_at=None,
        is_active=True,
    )

    try:
        db.add(user)
        db.flush()
        created_session = create_session(db, user.id, settings=settings)
        response = build_user_response(user)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _is_normalized_email_conflict(error):
            raise AccountConflictError("Account registration conflict.") from None
        raise
    except Exception:
        db.rollback()
        raise

    return RegistrationResult(
        user=response,
        raw_session_token=created_session.raw_token,
    )


def login_user(
    db: DbSession,
    login: LoginRequest,
    *,
    settings: Settings,
    direct_client_host: str | None,
    now: datetime | None = None,
) -> LoginResult:
    """Authenticate a password user and atomically create a new session."""

    email = normalize_email(login.email)
    candidate = login.password.get_secret_value()
    throttle_keys = build_login_throttle_keys(
        email.normalized,
        direct_client_host,
        settings=settings,
    )

    try:
        retry_after = get_login_retry_after(db, throttle_keys, now=now)
        if retry_after is not None:
            raise LoginRateLimitedError(retry_after)
        user = db.scalar(
            select(User)
            .options(selectinload(User.external_identities))
            .where(User.normalized_email == email.normalized)
        )
        if user is None or user.password_hash is None:
            verify_dummy_password(candidate)
            raise InvalidCredentialsError("Invalid credentials.")

        verified, replacement_hash = verify_and_update_password(
            candidate,
            user.password_hash,
        )
        if not verified or not user.is_active:
            raise InvalidCredentialsError("Invalid credentials.")

        if replacement_hash is not None:
            user.password_hash = replacement_hash
        reset_account_throttle(db, throttle_keys.account)
        created_session = create_session(db, user.id, settings=settings)
        response = build_user_response(user)
        db.commit()
    except LoginRateLimitedError:
        db.rollback()
        raise
    except InvalidCredentialsError:
        db.rollback()
        try:
            cleanup_expired_throttle_buckets(db, settings=settings, now=now)
            record_login_failure(
                db,
                throttle_keys,
                settings=settings,
                now=now,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        raise
    except Exception:
        db.rollback()
        raise

    return LoginResult(
        user=response,
        raw_session_token=created_session.raw_token,
    )


def logout_session(
    db: DbSession,
    raw_session_token: str | None,
    *,
    settings: Settings,
) -> None:
    """Revoke one valid session while treating absent or invalid tokens idempotently."""

    if raw_session_token is None:
        return

    try:
        resolved = resolve_session(db, raw_session_token, settings=settings)
        revoke_session(db, resolved.session_id)
        db.commit()
    except InvalidSessionError:
        db.rollback()
    except Exception:
        db.rollback()
        raise


def _is_normalized_email_conflict(error: IntegrityError) -> bool:
    return (
        isinstance(error.orig, UniqueViolation)
        and error.orig.diag.constraint_name == NORMALIZED_EMAIL_CONSTRAINT
    )
