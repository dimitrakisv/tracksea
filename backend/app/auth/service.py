from dataclasses import dataclass, field

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.auth.passwords import hash_password
from app.auth.schemas import RegistrationRequest
from app.auth.sessions import create_session
from app.core.config import Settings
from app.users.email import normalize_email
from app.users.models import User
from app.users.schemas import AuthenticationMethod, UserResponse
from app.users.service import normalize_display_name

NORMALIZED_EMAIL_CONSTRAINT = "uq_users_normalized_email"


class AccountConflictError(Exception):
    """A generic registration conflict that reveals no account details."""


@dataclass(frozen=True, slots=True)
class RegistrationResult:
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
        response = UserResponse(
            id=user.id,
            email=user.email,
            email_verified=False,
            display_name=user.display_name,
            authentication_methods=(AuthenticationMethod.PASSWORD,),
        )
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


def _is_normalized_email_conflict(error: IntegrityError) -> bool:
    return (
        isinstance(error.orig, UniqueViolation)
        and error.orig.diag.constraint_name == NORMALIZED_EMAIL_CONSTRAINT
    )
