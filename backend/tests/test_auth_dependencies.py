import json
from collections.abc import Generator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, NoReturn, cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import delete, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession
from starlette.requests import Request
from starlette.types import Scope

import app.auth.dependencies as auth_dependencies
from app.auth.dependencies import (
    AuthenticatedUser,
    get_optional_current_user,
    require_current_user,
)
from app.auth.models import Session
from app.auth.sessions import generate_session_token, hash_session_token
from app.core.config import Settings
from app.db.session import create_db_engine
from app.main import create_app
from app.users.models import User

TEST_EMAIL_PREFIX = "step8-auth-dependency-"
PASSWORD_HASH = "sensitive-password-hash"
GENERIC_AUTH_DETAIL = {
    "code": "authentication_required",
    "message": "Authentication is required.",
}


@dataclass(frozen=True, slots=True)
class AuthRecord:
    user_id: UUID
    session_id: UUID
    raw_token: str
    token_hash: bytes
    expires_at: datetime
    last_seen_at: datetime | None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(session_last_seen_interval_seconds=5 * 60)


@pytest.fixture
def auth_engine(auth_settings: Settings) -> Generator[Engine, None, None]:
    url = make_url(auth_settings.database_url)
    if url.host not in {"127.0.0.1", "localhost", "postgres"}:
        pytest.fail("Authentication tests require a local PostgreSQL database.")

    engine = create_db_engine(auth_settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.fail("Local PostgreSQL must be available for authentication tests.")

    yield engine

    with DbSession(engine) as db:
        db.execute(
            delete(User).where(User.normalized_email.like(f"{TEST_EMAIL_PREFIX}%"))
        )
        db.commit()
    engine.dispose()


def make_request(
    settings: Settings,
    raw_token: str | None = None,
    *,
    extra_headers: tuple[tuple[bytes, bytes], ...] = (),
    query_string: bytes = b"",
) -> Request:
    headers = list(extra_headers)
    if raw_token is not None:
        cookie = f"{settings.effective_session_cookie_name}={raw_token}"
        headers.append((b"cookie", cookie.encode("ascii")))
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/test",
        "raw_path": b"/test",
        "query_string": query_string,
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def create_auth_record(
    engine: Engine,
    *,
    is_active: bool = True,
    expires_at: datetime | None = None,
    last_seen_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> AuthRecord:
    now = datetime.now(UTC)
    selected_expiry = expires_at or now + timedelta(hours=1)
    created_at = min(now - timedelta(hours=1), selected_expiry - timedelta(hours=1))
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    suffix = uuid4().hex

    with DbSession(engine, expire_on_commit=False) as db:
        user = User(
            email=f"{TEST_EMAIL_PREFIX}{suffix}@example.test",
            normalized_email=f"{TEST_EMAIL_PREFIX}{suffix}@example.test",
            display_name="Dependency Observer",
            password_hash=PASSWORD_HASH,
            is_active=is_active,
        )
        db.add(user)
        db.flush()
        session = Session(
            user_id=user.id,
            token_hash=token_hash,
            created_at=created_at,
            expires_at=selected_expiry,
            last_seen_at=last_seen_at,
            revoked_at=revoked_at,
        )
        db.add(session)
        db.flush()
        record = AuthRecord(
            user_id=user.id,
            session_id=session.id,
            raw_token=raw_token,
            token_hash=token_hash,
            expires_at=selected_expiry,
            last_seen_at=last_seen_at,
        )
        db.commit()
    return record


def authenticate(
    engine: Engine,
    settings: Settings,
    raw_token: str | None,
    *,
    extra_headers: tuple[tuple[bytes, bytes], ...] = (),
    query_string: bytes = b"",
) -> AuthenticatedUser | None:
    request = make_request(
        settings,
        raw_token,
        extra_headers=extra_headers,
        query_string=query_string,
    )
    with DbSession(engine, expire_on_commit=False) as db:
        return get_optional_current_user(request, db, settings)


def load_session(engine: Engine, session_id: UUID) -> Session:
    with DbSession(engine) as db:
        record = db.get(Session, session_id)
        assert record is not None
        db.expunge(record)
        return record


def assert_generic_authentication_error(
    error: HTTPException,
    *,
    secrets: tuple[str, ...] = (),
) -> None:
    assert error.status_code == 401
    detail = cast(dict[str, str], error.detail)
    assert detail == GENERIC_AUTH_DETAIL
    serialized = json.dumps(detail)
    for secret in secrets:
        assert secret not in serialized
    assert "expired" not in serialized
    assert "revoked" not in serialized
    assert "inactive" not in serialized


def test_missing_cookie_returns_none_without_session_lookup(
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup_called = False

    def reject_lookup(*args: object, **kwargs: object) -> NoReturn:
        nonlocal lookup_called
        lookup_called = True
        raise AssertionError("Session lookup must not run without a cookie.")

    monkeypatch.setattr(auth_dependencies, "resolve_session", reject_lookup)
    with DbSession() as db:
        current_user = get_optional_current_user(
            make_request(auth_settings),
            db,
            auth_settings,
        )

    assert current_user is None
    assert not lookup_called


def test_only_the_configured_session_cookie_is_used(
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_settings = auth_settings.model_copy(
        update={"session_cookie_name": "custom_tracksea_session"}
    )

    def reject_lookup(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("An unconfigured cookie must not trigger a lookup.")

    monkeypatch.setattr(auth_dependencies, "resolve_session", reject_lookup)
    request = make_request(
        configured_settings,
        extra_headers=((b"cookie", b"tracksea_session=not-trusted"),),
    )
    with DbSession() as db:
        current_user = get_optional_current_user(
            request,
            db,
            configured_settings,
        )

    assert current_user is None


@pytest.mark.anyio
async def test_required_dependency_rejects_anonymous_user() -> None:
    with pytest.raises(HTTPException) as error:
        await require_current_user(None)

    assert_generic_authentication_error(error.value)


@pytest.mark.anyio
async def test_required_dependency_returns_authenticated_user() -> None:
    expected = AuthenticatedUser(id=uuid4(), is_active=True)

    assert await require_current_user(expected) == expected


@pytest.mark.anyio
async def test_required_http_error_ignores_alternative_credentials() -> None:
    app = FastAPI()

    async def anonymous_user() -> None:
        return None

    app.dependency_overrides[get_optional_current_user] = anonymous_user

    @app.get("/required")
    async def required_route(
        current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    ) -> dict[str, str]:
        return {"id": str(current_user.id)}

    transport = httpx.ASGITransport(app=app)
    bearer = "Bearer browser-token-is-not-supported"
    user_header = str(uuid4())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/required?user_id=browser-controlled",
            headers={"Authorization": bearer, "X-User-ID": user_header},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": GENERIC_AUTH_DETAIL}
    assert bearer not in response.text
    assert user_header not in response.text
    assert "browser-controlled" not in response.text
    assert "www-authenticate" not in response.headers


def test_alternative_credentials_do_not_trigger_authentication_lookup(
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_lookup(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Only the session cookie may trigger authentication.")

    monkeypatch.setattr(auth_dependencies, "resolve_session", reject_lookup)
    request = make_request(
        auth_settings,
        extra_headers=(
            (b"authorization", b"Bearer unsupported-token"),
            (b"x-user-id", str(uuid4()).encode("ascii")),
        ),
        query_string=b"user_id=browser-controlled",
    )
    with DbSession() as db:
        current_user = get_optional_current_user(request, db, auth_settings)

    assert current_user is None


def test_valid_session_returns_minimal_active_user_and_persists_first_seen(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    record = create_auth_record(auth_engine)
    before = datetime.now(UTC)

    current_user = authenticate(
        auth_engine,
        auth_settings,
        record.raw_token,
    )
    after = datetime.now(UTC)

    assert current_user == AuthenticatedUser(id=record.user_id, is_active=True)
    assert asdict(current_user) == {"id": record.user_id, "is_active": True}
    assert not hasattr(current_user, "password_hash")
    assert not hasattr(current_user, "token_hash")
    assert PASSWORD_HASH not in repr(current_user)
    assert record.raw_token not in repr(current_user)
    assert record.token_hash.hex() not in repr(current_user)

    persisted = load_session(auth_engine, record.session_id)
    assert persisted.last_seen_at is not None
    assert before <= persisted.last_seen_at <= after
    assert persisted.expires_at == record.expires_at


def test_stale_last_seen_is_updated_without_extending_absolute_expiry(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    stale = datetime.now(UTC) - timedelta(minutes=10)
    record = create_auth_record(auth_engine, last_seen_at=stale)
    before = datetime.now(UTC)

    authenticate(auth_engine, auth_settings, record.raw_token)
    after = datetime.now(UTC)

    persisted = load_session(auth_engine, record.session_id)
    assert persisted.last_seen_at is not None
    assert before <= persisted.last_seen_at <= after
    assert persisted.expires_at == record.expires_at


def test_recent_last_seen_is_not_rewritten(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    recent = datetime.now(UTC) - timedelta(minutes=1)
    record = create_auth_record(auth_engine, last_seen_at=recent)

    authenticate(auth_engine, auth_settings, record.raw_token)

    persisted = load_session(auth_engine, record.session_id)
    assert persisted.last_seen_at == recent
    assert persisted.expires_at == record.expires_at


def test_unknown_token_is_generic_and_does_not_update_other_session(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    stale = datetime.now(UTC) - timedelta(minutes=10)
    unrelated = create_auth_record(auth_engine, last_seen_at=stale)
    unknown = "unknown-opaque-session-token"

    with pytest.raises(HTTPException) as error:
        authenticate(auth_engine, auth_settings, unknown)

    assert_generic_authentication_error(error.value, secrets=(unknown,))
    persisted = load_session(auth_engine, unrelated.session_id)
    assert persisted.last_seen_at == stale


def test_expired_session_is_generic_and_does_not_update_last_seen(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    stale = datetime.now(UTC) - timedelta(minutes=10)
    record = create_auth_record(
        auth_engine,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        last_seen_at=stale,
    )

    with pytest.raises(HTTPException) as error:
        authenticate(auth_engine, auth_settings, record.raw_token)

    assert_generic_authentication_error(error.value, secrets=(record.raw_token,))
    persisted = load_session(auth_engine, record.session_id)
    assert persisted.last_seen_at == stale
    assert persisted.expires_at == record.expires_at


def test_revoked_session_is_generic_and_does_not_update_last_seen(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    stale = datetime.now(UTC) - timedelta(minutes=10)
    record = create_auth_record(
        auth_engine,
        last_seen_at=stale,
        revoked_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    with pytest.raises(HTTPException) as error:
        authenticate(auth_engine, auth_settings, record.raw_token)

    assert_generic_authentication_error(error.value, secrets=(record.raw_token,))
    persisted = load_session(auth_engine, record.session_id)
    assert persisted.last_seen_at == stale
    assert persisted.expires_at == record.expires_at


def test_inactive_user_is_generic_and_does_not_persist_last_seen(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    stale = datetime.now(UTC) - timedelta(minutes=10)
    record = create_auth_record(
        auth_engine,
        is_active=False,
        last_seen_at=stale,
    )

    with pytest.raises(HTTPException) as error:
        authenticate(auth_engine, auth_settings, record.raw_token)

    assert_generic_authentication_error(error.value, secrets=(record.raw_token,))
    persisted = load_session(auth_engine, record.session_id)
    assert persisted.last_seen_at == stale
    assert persisted.expires_at == record.expires_at


@pytest.mark.anyio
async def test_health_route_remains_public_without_authentication() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
