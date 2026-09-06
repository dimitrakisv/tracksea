from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app.auth.google import GoogleCredentialVerifier, VerifiedGoogleIdentity
from app.auth.passwords import (
    hash_password,
    verify_and_update_password,
    verify_dummy_password,
)
from app.auth.schemas import GoogleSignInRequest, LoginRequest, RegistrationRequest
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
from app.users.email import InvalidEmailError, NormalizedEmail, normalize_email
from app.users.models import ExternalIdentity, User
from app.users.schemas import UserResponse
from app.users.service import (
    InvalidDisplayNameError,
    build_user_response,
    normalize_display_name,
)

NORMALIZED_EMAIL_CONSTRAINT = "uq_users_normalized_email"
EXTERNAL_IDENTITY_CONSTRAINT = "uq_external_identities_provider_subject"
GOOGLE_PROVIDER = "google"
GOOGLE_DISPLAY_NAME_FALLBACK = "Marine Observer"


class AccountConflictError(Exception):
    """A generic registration conflict that reveals no account details."""


class InvalidCredentialsError(Exception):
    """A generic password-authentication failure safe for the HTTP boundary."""


class GoogleSignInInvalidCredentialsError(Exception):
    """A generic Google-authentication failure safe for the HTTP boundary."""


class GoogleAccountLinkRequiredError(Exception):
    """A verified Google email belongs to an existing unlinked account."""


class GoogleLinkInvalidCredentialsError(Exception):
    """Provider evidence is insufficient for explicit account linking."""


class GoogleLinkConflictError(Exception):
    """The requested identity cannot be linked to the current account."""


class GoogleLinkAuthenticationRequiredError(Exception):
    """The persisted current user is no longer available for linking."""


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user: UserResponse
    raw_session_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: UserResponse
    raw_session_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class GoogleSignInResult:
    user: UserResponse
    raw_session_token: str = field(repr=False)
    created: bool = False


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


def google_sign_in(
    db: DbSession,
    request: GoogleSignInRequest,
    verifier: GoogleCredentialVerifier,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> GoogleSignInResult:
    """Verify Google evidence and atomically create a TrackSea session."""

    verified = verifier.verify(request.credential.get_secret_value())
    signed_in_at = _as_utc(now)
    normalized_email: NormalizedEmail | None = None

    try:
        existing = _load_google_identity_user(db, verified.subject)
        if existing is not None:
            identity, user = existing
            return _complete_google_login(
                db,
                identity,
                user,
                settings=settings,
                signed_in_at=signed_in_at,
            )

        if not verified.email_verified:
            raise GoogleSignInInvalidCredentialsError(
                "Google sign-in could not be completed."
            )
        try:
            normalized_email = normalize_email(verified.email)
        except InvalidEmailError:
            raise GoogleSignInInvalidCredentialsError(
                "Google sign-in could not be completed."
            ) from None

        if _normalized_email_is_occupied(db, normalized_email.normalized):
            raise GoogleAccountLinkRequiredError("Account linking is required.")

        return _create_google_user(
            db,
            verified,
            normalized_email,
            settings=settings,
            signed_in_at=signed_in_at,
        )
    except IntegrityError as error:
        db.rollback()
        if not _is_expected_google_race(error):
            raise
        return _recover_google_sign_in_race(
            db,
            verified,
            normalized_email,
            error,
            settings=settings,
            signed_in_at=signed_in_at,
        )
    except Exception:
        db.rollback()
        raise


def link_google_identity(
    db: DbSession,
    current_user_id: UUID,
    request: GoogleSignInRequest,
    verifier: GoogleCredentialVerifier,
) -> UserResponse:
    """Explicitly link verified Google evidence to one password account."""

    verified = verifier.verify(request.credential.get_secret_value())
    if not verified.email_verified:
        raise GoogleLinkInvalidCredentialsError("Google account could not be verified.")
    try:
        email = normalize_email(verified.email)
    except InvalidEmailError:
        raise GoogleLinkInvalidCredentialsError(
            "Google account could not be verified."
        ) from None

    try:
        user = _load_google_link_user(db, current_user_id)
        _require_google_link_eligible_user(user, email)
        existing = _load_google_identity(db, verified.subject)
        if existing is not None:
            if existing.user_id != user.id:
                raise GoogleLinkConflictError("Google account could not be linked.")
            response = build_user_response(user)
            db.commit()
            return response

        user.external_identities.append(
            ExternalIdentity(
                provider=GOOGLE_PROVIDER,
                subject=verified.subject,
                email_snapshot=email.canonical,
                last_login_at=None,
            )
        )
        db.flush()
        response = build_user_response(user)
        db.commit()
        return response
    except IntegrityError as error:
        db.rollback()
        if not _is_external_identity_conflict(error):
            raise
        return _recover_google_link_race(
            db,
            current_user_id,
            verified.subject,
            email,
            error,
        )
    except Exception:
        db.rollback()
        raise


def _load_google_link_user(db: DbSession, current_user_id: UUID) -> User:
    user = db.scalar(
        select(User)
        .options(selectinload(User.external_identities))
        .where(User.id == current_user_id)
        .with_for_update()
    )
    if user is None or not user.is_active:
        raise GoogleLinkAuthenticationRequiredError("Authentication is required.")
    return user


def _require_google_link_eligible_user(
    user: User,
    email: NormalizedEmail,
) -> None:
    if user.password_hash is None or user.normalized_email != email.normalized:
        raise GoogleLinkConflictError("Google account could not be linked.")


def _load_google_identity(
    db: DbSession,
    subject: str,
) -> ExternalIdentity | None:
    return db.scalar(
        select(ExternalIdentity)
        .where(
            ExternalIdentity.provider == GOOGLE_PROVIDER,
            ExternalIdentity.subject == subject,
        )
        .with_for_update()
    )


def _recover_google_link_race(
    db: DbSession,
    current_user_id: UUID,
    subject: str,
    email: NormalizedEmail,
    original_error: IntegrityError,
) -> UserResponse:
    try:
        user = _load_google_link_user(db, current_user_id)
        _require_google_link_eligible_user(user, email)
        existing = _load_google_identity(db, subject)
        if existing is None:
            raise original_error
        if existing.user_id != user.id:
            raise GoogleLinkConflictError("Google account could not be linked.")
        response = build_user_response(user)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def _load_google_identity_user(
    db: DbSession,
    subject: str,
) -> tuple[ExternalIdentity, User] | None:
    identity = db.scalar(
        select(ExternalIdentity)
        .where(
            ExternalIdentity.provider == GOOGLE_PROVIDER,
            ExternalIdentity.subject == subject,
        )
        .with_for_update()
    )
    if identity is None:
        return None

    user = db.scalar(
        select(User)
        .options(selectinload(User.external_identities))
        .where(User.id == identity.user_id)
        .with_for_update()
    )
    if user is None:
        raise RuntimeError("Google identity references a missing user.")
    return identity, user


def _complete_google_login(
    db: DbSession,
    identity: ExternalIdentity,
    user: User,
    *,
    settings: Settings,
    signed_in_at: datetime,
) -> GoogleSignInResult:
    if not user.is_active:
        raise GoogleSignInInvalidCredentialsError(
            "Google sign-in could not be completed."
        )

    identity.last_login_at = signed_in_at
    created_session = create_session(db, user.id, settings=settings, now=signed_in_at)
    response = build_user_response(user)
    db.commit()
    return GoogleSignInResult(
        user=response,
        raw_session_token=created_session.raw_token,
        created=False,
    )


def _create_google_user(
    db: DbSession,
    verified: VerifiedGoogleIdentity,
    email: NormalizedEmail,
    *,
    settings: Settings,
    signed_in_at: datetime,
) -> GoogleSignInResult:
    display_name = _google_display_name(verified.name)
    user = User(
        email=email.canonical,
        normalized_email=email.normalized,
        display_name=display_name,
        password_hash=None,
        email_verified_at=signed_in_at,
        is_active=True,
    )
    user.external_identities.append(
        ExternalIdentity(
            provider=GOOGLE_PROVIDER,
            subject=verified.subject,
            email_snapshot=email.canonical,
            last_login_at=signed_in_at,
        )
    )
    db.add(user)
    db.flush()
    created_session = create_session(db, user.id, settings=settings, now=signed_in_at)
    response = build_user_response(user)
    db.commit()
    return GoogleSignInResult(
        user=response,
        raw_session_token=created_session.raw_token,
        created=True,
    )


def _recover_google_sign_in_race(
    db: DbSession,
    verified: VerifiedGoogleIdentity,
    email: NormalizedEmail | None,
    original_error: IntegrityError,
    *,
    settings: Settings,
    signed_in_at: datetime,
) -> GoogleSignInResult:
    try:
        existing = _load_google_identity_user(db, verified.subject)
        if existing is not None:
            identity, user = existing
            return _complete_google_login(
                db,
                identity,
                user,
                settings=settings,
                signed_in_at=signed_in_at,
            )
        if email is not None and _normalized_email_is_occupied(db, email.normalized):
            raise GoogleAccountLinkRequiredError("Account linking is required.")
    except Exception:
        db.rollback()
        raise

    db.rollback()
    raise original_error


def _normalized_email_is_occupied(db: DbSession, normalized_email: str) -> bool:
    return (
        db.scalar(select(User.id).where(User.normalized_email == normalized_email))
        is not None
    )


def _google_display_name(name: str | None) -> str:
    if name is None:
        return GOOGLE_DISPLAY_NAME_FALLBACK
    try:
        return normalize_display_name(name)
    except InvalidDisplayNameError:
        return GOOGLE_DISPLAY_NAME_FALLBACK


def _is_expected_google_race(error: IntegrityError) -> bool:
    return isinstance(
        error.orig, UniqueViolation
    ) and error.orig.diag.constraint_name in {
        NORMALIZED_EMAIL_CONSTRAINT,
        EXTERNAL_IDENTITY_CONSTRAINT,
    }


def _is_external_identity_conflict(error: IntegrityError) -> bool:
    return (
        isinstance(error.orig, UniqueViolation)
        and error.orig.diag.constraint_name == EXTERNAL_IDENTITY_CONSTRAINT
    )


def _as_utc(value: datetime | None) -> datetime:
    selected = value or datetime.now(UTC)
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError("Google sign-in timestamps must be timezone-aware.")
    return selected.astimezone(UTC)


def _is_normalized_email_conflict(error: IntegrityError) -> bool:
    return (
        isinstance(error.orig, UniqueViolation)
        and error.orig.diag.constraint_name == NORMALIZED_EMAIL_CONSTRAINT
    )
