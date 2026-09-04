import base64
import logging
import re
import secrets
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession
from starlette.responses import Response

from app.auth.cookies import clear_session_cookie, set_session_cookie
from app.auth.models import Session
from app.auth.sessions import (
    SESSION_RANDOM_BYTES,
    InvalidSessionError,
    create_session,
    hash_session_token,
    resolve_session,
    revoke_session,
)
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine
from app.users.models import User
from app.users.schemas import UserResponse

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def db_session() -> Generator[DbSession, None, None]:
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.host not in {"127.0.0.1", "localhost", "postgres"}:
        pytest.fail("Session integration tests require a local PostgreSQL database.")

    engine = create_db_engine(settings)
    try:
        connection = engine.connect()
    except OperationalError:
        engine.dispose()
        pytest.skip("Local PostgreSQL is not available.")

    transaction = connection.begin()
    session = DbSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def session_settings() -> Settings:
    return Settings(
        session_lifetime_seconds=60 * 60,
        session_last_seen_interval_seconds=5 * 60,
    )


def create_user(db: DbSession) -> User:
    suffix = uuid4().hex
    user = User(
        email=f"observer-{suffix}@example.com",
        normalized_email=f"observer-{suffix}@example.com",
        display_name="Session Observer",
    )
    db.add(user)
    db.flush()
    return user


def test_session_tokens_use_32_random_bytes_and_are_cookie_safe(
    db_session: DbSession,
    session_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_lengths: list[int] = []

    def token_bytes(length: int) -> bytes:
        requested_lengths.append(length)
        return bytes(range(length))

    monkeypatch.setattr(secrets, "token_bytes", token_bytes)
    created = create_session(
        db_session,
        create_user(db_session).id,
        settings=session_settings,
        now=NOW,
    )

    assert requested_lengths == [SESSION_RANDOM_BYTES]
    assert SESSION_RANDOM_BYTES == 32
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", created.raw_token)
    padded_token = created.raw_token + "=" * (-len(created.raw_token) % 4)
    assert len(base64.urlsafe_b64decode(padded_token)) == 32


def test_created_sessions_are_unique_and_store_only_binary_digests(
    db_session: DbSession,
    session_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = create_user(db_session)
    with caplog.at_level(logging.DEBUG):
        first = create_session(db_session, user.id, settings=session_settings, now=NOW)
        second = create_session(db_session, user.id, settings=session_settings, now=NOW)

    first_record = db_session.get(Session, first.session_id)
    second_record = db_session.get(Session, second.session_id)
    assert first_record is not None
    assert second_record is not None
    assert first.raw_token != second.raw_token
    assert len(first_record.token_hash) == 32
    assert first_record.token_hash == hash_session_token(first.raw_token)
    assert second_record.token_hash == hash_session_token(second.raw_token)
    assert first.raw_token.encode() != first_record.token_hash
    assert first.raw_token not in repr(first)
    assert first.raw_token not in caplog.text
    assert second.raw_token not in caplog.text


def test_new_session_resolves_with_user_and_absolute_expiration(
    db_session: DbSession,
    session_settings: Settings,
) -> None:
    user = create_user(db_session)
    created = create_session(db_session, user.id, settings=session_settings, now=NOW)

    resolved = resolve_session(
        db_session,
        created.raw_token,
        settings=session_settings,
        now=NOW + timedelta(seconds=1),
    )

    assert resolved.session_id == created.session_id
    assert resolved.user.id == user.id
    assert created.expires_at == NOW + timedelta(hours=1)
    assert resolved.expires_at == created.expires_at


def test_unknown_token_is_rejected_without_echoing_it(
    db_session: DbSession,
    session_settings: Settings,
) -> None:
    unknown_token = "unknown_browser_session_token"

    with pytest.raises(InvalidSessionError) as error:
        resolve_session(
            db_session,
            unknown_token,
            settings=session_settings,
            now=NOW,
        )

    assert str(error.value) == "Session is not active."
    assert unknown_token not in str(error.value)


def test_expired_session_is_rejected(
    db_session: DbSession,
    session_settings: Settings,
) -> None:
    created = create_session(
        db_session,
        create_user(db_session).id,
        settings=session_settings,
        now=NOW - timedelta(hours=2),
    )

    with pytest.raises(InvalidSessionError):
        resolve_session(
            db_session,
            created.raw_token,
            settings=session_settings,
            now=NOW,
        )


def test_revocation_is_persisted_and_scoped_to_one_session(
    db_session: DbSession,
    session_settings: Settings,
) -> None:
    user = create_user(db_session)
    revoked = create_session(db_session, user.id, settings=session_settings, now=NOW)
    active = create_session(db_session, user.id, settings=session_settings, now=NOW)

    assert revoke_session(
        db_session,
        revoked.session_id,
        now=NOW + timedelta(minutes=1),
    )
    db_session.expire_all()
    revoked_record = db_session.get(Session, revoked.session_id)
    assert revoked_record is not None
    assert revoked_record.revoked_at == NOW + timedelta(minutes=1)
    with pytest.raises(InvalidSessionError):
        resolve_session(
            db_session,
            revoked.raw_token,
            settings=session_settings,
            now=NOW + timedelta(minutes=2),
        )
    assert (
        resolve_session(
            db_session,
            active.raw_token,
            settings=session_settings,
            now=NOW + timedelta(minutes=2),
        ).session_id
        == active.session_id
    )


def test_revoke_unknown_session_returns_false(db_session: DbSession) -> None:
    assert not revoke_session(db_session, uuid4(), now=NOW)


def test_last_seen_updates_only_after_the_interval_without_extending_expiry(
    db_session: DbSession,
    session_settings: Settings,
) -> None:
    user = create_user(db_session)
    null_seen = create_session(db_session, user.id, settings=session_settings, now=NOW)
    stale_seen = create_session(db_session, user.id, settings=session_settings, now=NOW)
    recent_seen = create_session(
        db_session, user.id, settings=session_settings, now=NOW
    )
    stale_record = db_session.get(Session, stale_seen.session_id)
    recent_record = db_session.get(Session, recent_seen.session_id)
    assert stale_record is not None
    assert recent_record is not None
    stale_record.last_seen_at = NOW - timedelta(minutes=6)
    recent_value = NOW - timedelta(minutes=1)
    recent_record.last_seen_at = recent_value
    db_session.flush()
    expiry = recent_record.expires_at

    resolve_session(
        db_session,
        null_seen.raw_token,
        settings=session_settings,
        now=NOW,
    )
    resolve_session(
        db_session,
        stale_seen.raw_token,
        settings=session_settings,
        now=NOW,
    )
    db_session.expire_all()
    null_record = db_session.get(Session, null_seen.session_id)
    stale_record = db_session.get(Session, stale_seen.session_id)
    assert null_record is not None
    assert stale_record is not None
    assert null_record.last_seen_at == NOW
    assert stale_record.last_seen_at == NOW

    update_statements: list[str] = []

    def capture_updates(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith("UPDATE SESSIONS"):
            update_statements.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", capture_updates)
    try:
        resolved = resolve_session(
            db_session,
            recent_seen.raw_token,
            settings=session_settings,
            now=NOW,
        )
    finally:
        event.remove(connection, "before_cursor_execute", capture_updates)
    db_session.expire_all()
    recent_record = db_session.get(Session, recent_seen.session_id)
    assert recent_record is not None
    assert recent_record.last_seen_at == recent_value
    assert recent_record.expires_at == expiry
    assert resolved.expires_at == expiry
    assert update_statements == []


def test_session_model_and_public_schema_expose_no_session_credentials() -> None:
    assert "raw_token" not in Session.__table__.columns
    assert "token" not in UserResponse.model_fields
    assert "token_hash" not in UserResponse.model_fields


def test_local_session_cookie_attributes() -> None:
    settings = Settings(
        session_cookie_name="tracksea_session",
        session_cookie_secure=False,
        session_lifetime_seconds=60 * 60,
    )
    response = Response()

    set_session_cookie(response, "opaque_cookie_token", settings=settings)

    header = response.headers["set-cookie"]
    assert header.startswith("tracksea_session=opaque_cookie_token;")
    assert "HttpOnly" in header
    assert "Max-Age=3600" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header
    assert "Secure" not in header
    assert "Domain=" not in header


def test_production_session_cookie_attributes() -> None:
    settings = Settings(
        environment="production",
        session_cookie_secure=True,
        session_cookie_name=None,
    )
    response = Response()

    set_session_cookie(response, "opaque_cookie_token", settings=settings)

    header = response.headers["set-cookie"]
    assert header.startswith("__Host-tracksea_session=opaque_cookie_token;")
    assert "HttpOnly" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header
    assert "Secure" in header
    assert "Domain=" not in header


def test_nonlocal_session_cookie_must_be_secure() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", session_cookie_secure=False)


@pytest.mark.parametrize("secure", [False, True])
def test_clearing_session_cookie_preserves_matching_policy(secure: bool) -> None:
    settings = Settings(
        environment="production" if secure else "local",
        session_cookie_secure=secure,
        session_cookie_name="__Host-tracksea_session" if secure else "tracksea_session",
    )
    response = Response()

    clear_session_cookie(response, settings=settings)

    header = response.headers["set-cookie"]
    assert header.startswith(f'{settings.effective_session_cookie_name}="";')
    assert "HttpOnly" in header
    assert "Max-Age=0" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header
    assert ("Secure" in header) is secure
    assert "Domain=" not in header


def test_cookie_header_does_not_expose_internal_digest() -> None:
    raw_token = "opaque_cookie_token"
    digest = hash_session_token(raw_token)
    response = Response()

    set_session_cookie(response, raw_token)

    header = response.headers["set-cookie"]
    assert digest.hex() not in header
    assert repr(digest) not in header
