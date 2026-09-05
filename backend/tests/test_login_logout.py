from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, NoReturn
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pydantic import SecretStr
from sqlalchemy import delete, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

import app.auth.service as auth_service
from app.auth.csrf import CsrfValidationError, validate_csrf_token
from app.auth.dependencies import AuthenticatedUser, require_current_user
from app.auth.models import Session
from app.auth.passwords import (
    hash_password,
    verify_and_update_password,
    verify_password,
)
from app.auth.sessions import (
    InvalidSessionError,
    create_session,
    hash_session_token,
    resolve_session,
    revoke_session,
)
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, get_db_session
from app.main import create_app
from app.users.email import normalize_email
from app.users.models import ExternalIdentity, User

TEST_EMAIL_PREFIX = "step10-auth-"
VALID_PASSWORD = "a private ocean passphrase"
WRONG_PASSWORD = "an incorrect ocean passphrase"
TEST_CSRF_SECRET = SecretStr("test-csrf-secret-with-at-least-32-bytes")
INVALID_CREDENTIALS_DETAIL = {
    "detail": {
        "code": "invalid_credentials",
        "message": "Email or password is incorrect.",
    }
}
CSRF_FAILURE_DETAIL = {
    "detail": {
        "code": "csrf_failed",
        "message": "Request could not be verified.",
    }
}


@dataclass(frozen=True, slots=True)
class LoginHttpResult:
    bootstrap_token: str
    response: httpx.Response
    session_token: str | None
    csrf_token: str | None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def auth_settings() -> Settings:
    return Settings()


@pytest.fixture
def auth_engine(auth_settings: Settings) -> Generator[Engine, None, None]:
    url = make_url(auth_settings.database_url)
    if url.host not in {"127.0.0.1", "localhost", "postgres"}:
        pytest.fail("Login/logout tests require a local PostgreSQL database.")

    engine = create_db_engine(auth_settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.fail("Local PostgreSQL must be available for login/logout tests.")

    yield engine

    with DbSession(engine) as db:
        db.execute(
            delete(User).where(User.normalized_email.like(f"{TEST_EMAIL_PREFIX}%"))
        )
        db.commit()
    engine.dispose()


def build_auth_app(engine: Engine, settings: Settings) -> FastAPI:
    app = create_app()

    def database_override() -> Generator[DbSession, None, None]:
        with DbSession(engine, expire_on_commit=False) as db:
            yield db

    async def settings_override() -> Settings:
        return settings

    @app.get("/_test/current")
    async def test_current_user(
        current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    ) -> dict[str, str]:
        return {"id": str(current_user.id)}

    app.dependency_overrides[get_db_session] = database_override
    app.dependency_overrides[get_settings] = settings_override
    return app


def unique_email(*, suffix: str = "") -> str:
    return f"{TEST_EMAIL_PREFIX}{uuid4().hex}{suffix}@example.com"


def create_user(
    engine: Engine,
    *,
    email: str,
    password: str | None = VALID_PASSWORD,
    password_hash: str | None = None,
    is_active: bool = True,
    google_identity: bool = False,
    verified: bool = False,
) -> UUID:
    normalized = normalize_email(email)
    stored_hash = (
        password_hash
        if password_hash is not None
        else hash_password(password)
        if password is not None
        else None
    )
    with DbSession(engine, expire_on_commit=False) as db:
        user = User(
            email=normalized.canonical,
            normalized_email=normalized.normalized,
            display_name="Login Observer",
            password_hash=stored_hash,
            email_verified_at=datetime.now(UTC) if verified else None,
            is_active=is_active,
        )
        db.add(user)
        db.flush()
        if google_identity:
            db.add(
                ExternalIdentity(
                    user_id=user.id,
                    provider="google",
                    subject=f"google-{uuid4().hex}",
                    email_snapshot=user.email,
                )
            )
        db.commit()
        return user.id


def create_persisted_session(
    engine: Engine,
    settings: Settings,
    user_id: UUID,
    *,
    now: datetime | None = None,
    revoked: bool = False,
) -> tuple[UUID, str]:
    with DbSession(engine) as db:
        created = create_session(db, user_id, settings=settings, now=now)
        if revoked:
            revoke_session(db, created.session_id)
        db.commit()
        return created.session_id, created.raw_token


def session_records(engine: Engine, user_id: UUID) -> list[Session]:
    with DbSession(engine) as db:
        records = list(
            db.scalars(
                select(Session)
                .where(Session.user_id == user_id)
                .order_by(Session.created_at, Session.id)
            )
        )
        for record in records:
            db.expunge(record)
        return records


def stored_user(engine: Engine, user_id: UUID) -> User:
    with DbSession(engine) as db:
        user = db.get(User, user_id)
        assert user is not None
        db.expunge(user)
        return user


async def bootstrap_csrf(client: httpx.AsyncClient) -> str:
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


async def post_login(
    app: FastAPI,
    settings: Settings,
    *,
    email: str,
    password: str,
    incoming_session: str | None = None,
    origin: str | None = None,
    extra: dict[str, str] | None = None,
    raise_app_exceptions: bool = True,
) -> LoginHttpResult:
    transport = httpx.ASGITransport(
        app=app,
        raise_app_exceptions=raise_app_exceptions,
    )
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        if incoming_session is not None:
            set_browser_session_cookie(
                client,
                settings.effective_session_cookie_name,
                incoming_session,
            )
        bootstrap_token = await bootstrap_csrf(client)
        payload = {"email": email, "password": password}
        if extra is not None:
            payload.update(extra)
        response = await client.post(
            "/api/v1/auth/login",
            json=payload,
            headers={
                settings.csrf_header_name: bootstrap_token,
                "Origin": origin or str(settings.frontend_origin).rstrip("/"),
            },
        )
        session_token = response.cookies.get(settings.effective_session_cookie_name)
        csrf_token = response.cookies.get(settings.effective_csrf_cookie_name)

    return LoginHttpResult(
        bootstrap_token=bootstrap_token,
        response=response,
        session_token=session_token,
        csrf_token=csrf_token,
    )


def cookie_header(response: httpx.Response, name: str) -> str:
    return next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{name}=")
    )


def set_browser_session_cookie(
    client: httpx.AsyncClient,
    name: str,
    value: str,
) -> None:
    client.cookies.set(name, value, domain="testserver.local", path="/")


@pytest.mark.anyio
async def test_password_login_returns_safe_user_and_new_session(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    suffix = uuid4().hex
    canonical_email = f"Step10-Auth-{suffix}+tag@example.com"
    login_email = f" STEP10-AUTH-{suffix.upper()}+TAG@EXAMPLE.COM "
    password = "  μια ασφαλής σύνδεση στη θάλασσα  "
    user_id = create_user(
        auth_engine,
        email=canonical_email,
        password=password,
        google_identity=True,
        verified=True,
    )
    app = build_auth_app(auth_engine, auth_settings)

    result = await post_login(
        app,
        auth_settings,
        email=login_email,
        password=password,
    )

    assert result.response.status_code == 200, result.response.text
    body = result.response.json()
    assert body == {
        "id": str(user_id),
        "email": canonical_email,
        "email_verified": True,
        "display_name": "Login Observer",
        "authentication_methods": ["password", "google"],
    }
    for private_field in (
        "normalized_email",
        "password_hash",
        "session_id",
        "token_hash",
        "raw_session_token",
        "subject",
        "csrf_secret",
    ):
        assert private_field not in body
    assert password not in result.response.text
    assert "www-authenticate" not in result.response.headers

    assert result.session_token is not None
    assert result.csrf_token is not None
    records = session_records(auth_engine, user_id)
    assert len(records) == 1
    assert len(records[0].token_hash) == 32
    assert records[0].token_hash == hash_session_token(result.session_token)
    assert records[0].token_hash != result.session_token.encode()
    validate_csrf_token(
        result.csrf_token,
        settings=auth_settings,
        session_token=result.session_token,
    )
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(
            result.bootstrap_token,
            settings=auth_settings,
            session_token=result.session_token,
        )

    session_cookie = cookie_header(
        result.response,
        auth_settings.effective_session_cookie_name,
    )
    csrf_cookie = cookie_header(
        result.response,
        auth_settings.effective_csrf_cookie_name,
    )
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "Secure" not in session_cookie
    assert "Domain=" not in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Path=/" in csrf_cookie


@pytest.mark.anyio
async def test_login_preserves_plus_tag_lookup_behavior(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    suffix = uuid4().hex
    tagged = f"{TEST_EMAIL_PREFIX}{suffix}+journal@example.com"
    untagged = f"{TEST_EMAIL_PREFIX}{suffix}@example.com"
    user_id = create_user(auth_engine, email=tagged)
    app = build_auth_app(auth_engine, auth_settings)

    tagged_result = await post_login(
        app,
        auth_settings,
        email=tagged,
        password=VALID_PASSWORD,
    )
    untagged_result = await post_login(
        app,
        auth_settings,
        email=untagged,
        password=VALID_PASSWORD,
    )

    assert tagged_result.response.status_code == 200
    assert untagged_result.response.status_code == 401
    assert untagged_result.response.json() == INVALID_CREDENTIALS_DETAIL
    assert len(session_records(auth_engine, user_id)) == 1


@pytest.mark.anyio
async def test_login_schema_rejects_malformed_email_and_extra_fields_without_secrets(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    app = build_auth_app(auth_engine, auth_settings)

    malformed = await post_login(
        app,
        auth_settings,
        email="not-an-email",
        password=VALID_PASSWORD,
    )
    extra = await post_login(
        app,
        auth_settings,
        email=unique_email(),
        password=VALID_PASSWORD,
        extra={"remember_me": "true"},
    )

    for result in (malformed, extra):
        assert result.response.status_code == 422
        assert VALID_PASSWORD not in result.response.text
        assert result.session_token is None


@pytest.mark.anyio
async def test_login_validation_does_not_echo_malformed_password_input(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    candidate = "candidate-that-must-not-be-returned"
    app = build_auth_app(auth_engine, auth_settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        csrf_token = await bootstrap_csrf(client)
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": unique_email(),
                "password": {"candidate": candidate},
            },
            headers={
                auth_settings.csrf_header_name: csrf_token,
                "Origin": "http://localhost:5173",
            },
        )

    assert response.status_code == 422
    assert candidate not in response.text
    assert "input" not in response.json()["detail"][0]


@pytest.mark.anyio
async def test_login_failures_are_generic_and_create_no_sessions(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    password_email = unique_email()
    google_email = unique_email()
    inactive_email = unique_email()
    unusable_email = unique_email()
    password_user_id = create_user(auth_engine, email=password_email)
    google_user_id = create_user(
        auth_engine,
        email=google_email,
        password=None,
        google_identity=True,
    )
    inactive_user_id = create_user(
        auth_engine,
        email=inactive_email,
        is_active=False,
    )
    unusable_user_id = create_user(
        auth_engine,
        email=unusable_email,
        password_hash="not-a-supported-password-hash",
    )
    app = build_auth_app(auth_engine, auth_settings)

    attempts = (
        (password_email, WRONG_PASSWORD),
        (unique_email(), WRONG_PASSWORD),
        (google_email, WRONG_PASSWORD),
        (inactive_email, VALID_PASSWORD),
        (unusable_email, WRONG_PASSWORD),
    )
    responses = []
    for email, password in attempts:
        result = await post_login(
            app,
            auth_settings,
            email=email,
            password=password,
        )
        responses.append(result.response)
        assert result.session_token is None

    for response in responses:
        assert response.status_code == 401
        assert response.json() == INVALID_CREDENTIALS_DETAIL
        assert "www-authenticate" not in response.headers
        assert WRONG_PASSWORD not in response.text
        assert VALID_PASSWORD not in response.text
        assert "google" not in response.text.casefold()
        assert "inactive" not in response.text.casefold()
    assert session_records(auth_engine, password_user_id) == []
    assert session_records(auth_engine, google_user_id) == []
    assert session_records(auth_engine, inactive_user_id) == []
    assert session_records(auth_engine, unusable_user_id) == []


@pytest.mark.anyio
async def test_unknown_and_passwordless_login_execute_dummy_verification(
    auth_engine: Engine,
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    google_email = unique_email()
    create_user(
        auth_engine,
        email=google_email,
        password=None,
        google_identity=True,
    )
    app = build_auth_app(auth_engine, auth_settings)
    calls = 0

    def observe_dummy_verification(candidate: str) -> bool:
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(
        auth_service,
        "verify_dummy_password",
        observe_dummy_verification,
    )

    unknown = await post_login(
        app,
        auth_settings,
        email=unique_email(),
        password=WRONG_PASSWORD,
    )
    passwordless = await post_login(
        app,
        auth_settings,
        email=google_email,
        password=WRONG_PASSWORD,
    )

    assert unknown.response.json() == INVALID_CREDENTIALS_DETAIL
    assert passwordless.response.json() == INVALID_CREDENTIALS_DETAIL
    assert calls == 2


@pytest.mark.anyio
async def test_inactive_password_user_executes_real_verification(
    auth_engine: Engine,
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = unique_email()
    user_id = create_user(auth_engine, email=email, is_active=False)
    app = build_auth_app(auth_engine, auth_settings)
    original = verify_and_update_password
    calls = 0

    def observe_real_verification(
        candidate: str,
        stored_hash: str,
    ) -> tuple[bool, str | None]:
        nonlocal calls
        calls += 1
        return original(candidate, stored_hash)

    monkeypatch.setattr(
        auth_service,
        "verify_and_update_password",
        observe_real_verification,
    )

    result = await post_login(
        app,
        auth_settings,
        email=email,
        password=VALID_PASSWORD,
    )

    assert result.response.status_code == 401
    assert result.response.json() == INVALID_CREDENTIALS_DETAIL
    assert calls == 1
    assert session_records(auth_engine, user_id) == []


@pytest.mark.anyio
async def test_successful_login_persists_required_password_rehash(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    email = unique_email()
    stale_hasher = PasswordHash((Argon2Hasher(time_cost=2),))
    stale_hash = stale_hasher.hash(VALID_PASSWORD)
    user_id = create_user(
        auth_engine,
        email=email,
        password_hash=stale_hash,
    )
    app = build_auth_app(auth_engine, auth_settings)

    result = await post_login(
        app,
        auth_settings,
        email=email,
        password=VALID_PASSWORD,
    )

    assert result.response.status_code == 200
    replacement_hash = stored_user(auth_engine, user_id).password_hash
    assert replacement_hash is not None
    assert replacement_hash != stale_hash
    assert verify_password(VALID_PASSWORD, replacement_hash)


@pytest.mark.anyio
async def test_failed_login_does_not_rehash_password(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    email = unique_email()
    stale_hasher = PasswordHash((Argon2Hasher(time_cost=2),))
    stale_hash = stale_hasher.hash(VALID_PASSWORD)
    user_id = create_user(
        auth_engine,
        email=email,
        password_hash=stale_hash,
    )
    app = build_auth_app(auth_engine, auth_settings)

    result = await post_login(
        app,
        auth_settings,
        email=email,
        password=WRONG_PASSWORD,
    )

    assert result.response.status_code == 401
    assert stored_user(auth_engine, user_id).password_hash == stale_hash
    assert session_records(auth_engine, user_id) == []


@pytest.mark.anyio
async def test_login_transaction_failure_rolls_back_rehash_and_cookie(
    auth_engine: Engine,
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = unique_email()
    stale_hasher = PasswordHash((Argon2Hasher(time_cost=2),))
    stale_hash = stale_hasher.hash(VALID_PASSWORD)
    user_id = create_user(
        auth_engine,
        email=email,
        password_hash=stale_hash,
    )
    app = build_auth_app(auth_engine, auth_settings)

    def fail_session_creation(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("controlled login session failure")

    monkeypatch.setattr(auth_service, "create_session", fail_session_creation)

    result = await post_login(
        app,
        auth_settings,
        email=email,
        password=VALID_PASSWORD,
        raise_app_exceptions=False,
    )

    assert result.response.status_code == 500
    assert result.session_token is None
    assert auth_settings.effective_csrf_cookie_name not in "".join(
        result.response.headers.get_list("set-cookie")
    )
    assert stored_user(auth_engine, user_id).password_hash == stale_hash
    assert session_records(auth_engine, user_id) == []


@pytest.mark.anyio
async def test_each_login_mints_a_distinct_session_without_revoking_older_one(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    email = unique_email()
    user_id = create_user(auth_engine, email=email)
    app = build_auth_app(auth_engine, auth_settings)
    incoming = "caller-selected-session-token"

    first = await post_login(
        app,
        auth_settings,
        email=email,
        password=VALID_PASSWORD,
        incoming_session=incoming,
    )
    assert first.session_token is not None
    second = await post_login(
        app,
        auth_settings,
        email=email,
        password=VALID_PASSWORD,
        incoming_session=first.session_token,
    )

    assert first.response.status_code == 200
    assert second.response.status_code == 200
    assert second.session_token is not None
    assert first.session_token != incoming
    assert second.session_token not in {incoming, first.session_token}
    records = session_records(auth_engine, user_id)
    assert len(records) == 2
    assert all(record.revoked_at is None for record in records)
    stored_hashes = {record.token_hash for record in records}
    assert stored_hashes == {
        hash_session_token(first.session_token),
        hash_session_token(second.session_token),
    }
    assert first.csrf_token is not None
    assert second.csrf_token is not None
    validate_csrf_token(
        second.csrf_token,
        settings=auth_settings,
        session_token=second.session_token,
    )
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(
            first.csrf_token,
            settings=auth_settings,
            session_token=second.session_token,
        )


@pytest.mark.anyio
async def test_login_requires_valid_csrf_and_origin(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    email = unique_email()
    user_id = create_user(auth_engine, email=email)
    app = build_auth_app(auth_engine, auth_settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        missing_header = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": VALID_PASSWORD},
            headers={"Origin": "http://localhost:5173"},
        )
        token = await bootstrap_csrf(client)
        invalid_origin = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": VALID_PASSWORD},
            headers={
                auth_settings.csrf_header_name: token,
                "Origin": "http://localhost:5173.evil.example",
            },
        )
        client.cookies.delete(auth_settings.effective_csrf_cookie_name)
        missing_cookie = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": VALID_PASSWORD},
            headers={
                auth_settings.csrf_header_name: token,
                "Origin": "http://localhost:5173",
            },
        )

    for response in (missing_header, invalid_origin, missing_cookie):
        assert response.status_code == 403
        assert response.json() == CSRF_FAILURE_DETAIL
    assert session_records(auth_engine, user_id) == []


@pytest.mark.anyio
async def test_valid_logout_revokes_only_current_session_and_rotates_to_anonymous_csrf(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    email = unique_email()
    user_id = create_user(auth_engine, email=email)
    current_id, current_token = create_persisted_session(
        auth_engine,
        auth_settings,
        user_id,
    )
    other_id, other_token = create_persisted_session(
        auth_engine,
        auth_settings,
        user_id,
    )
    app = build_auth_app(auth_engine, auth_settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        set_browser_session_cookie(
            client,
            auth_settings.effective_session_cookie_name,
            current_token,
        )
        bound_csrf = await bootstrap_csrf(client)
        before = await client.get("/_test/current")
        response = await client.post(
            "/api/v1/auth/logout",
            headers={
                auth_settings.csrf_header_name: bound_csrf,
                "Origin": "http://localhost:5173",
            },
        )
        anonymous_csrf = response.cookies.get(auth_settings.effective_csrf_cookie_name)
        after = await client.get("/_test/current")
        remaining_cookie = dict(client.cookies).get(
            auth_settings.effective_session_cookie_name
        )

    assert before.status_code == 200
    assert response.status_code == 204
    assert response.content == b""
    assert after.status_code == 401
    assert remaining_cookie is None
    deletion = cookie_header(response, auth_settings.effective_session_cookie_name)
    assert "Max-Age=0" in deletion
    assert "Path=/" in deletion
    assert "HttpOnly" in deletion
    assert "SameSite=lax" in deletion
    assert "Secure" not in deletion
    assert "Domain=" not in deletion

    assert anonymous_csrf is not None
    assert anonymous_csrf != bound_csrf
    validate_csrf_token(anonymous_csrf, settings=auth_settings)
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(bound_csrf, settings=auth_settings)

    records = {record.id: record for record in session_records(auth_engine, user_id)}
    assert records[current_id].revoked_at is not None
    assert records[other_id].revoked_at is None
    with DbSession(auth_engine) as db:
        with pytest.raises(InvalidSessionError):
            resolve_session(db, current_token, settings=auth_settings)
        resolved_other = resolve_session(db, other_token, settings=auth_settings)
        assert resolved_other.session_id == other_id
        db.rollback()


@pytest.mark.parametrize(
    "session_state",
    ["missing", "unknown", "expired", "revoked"],
)
@pytest.mark.anyio
async def test_logout_is_idempotent_for_absent_or_invalid_sessions(
    session_state: str,
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    user_id: UUID | None = None
    session_id: UUID | None = None
    raw_token: str | None = None
    if session_state == "unknown":
        raw_token = "unknown-session-token"
    elif session_state in {"expired", "revoked"}:
        user_id = create_user(auth_engine, email=unique_email())
        session_id, raw_token = create_persisted_session(
            auth_engine,
            auth_settings,
            user_id,
            now=(
                datetime.now(UTC) - timedelta(days=31)
                if session_state == "expired"
                else None
            ),
            revoked=session_state == "revoked",
        )

    app = build_auth_app(auth_engine, auth_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        if raw_token is not None:
            set_browser_session_cookie(
                client,
                auth_settings.effective_session_cookie_name,
                raw_token,
            )
        csrf_token = await bootstrap_csrf(client)
        first = await client.post(
            "/api/v1/auth/logout",
            headers={
                auth_settings.csrf_header_name: csrf_token,
                "Origin": "http://localhost:5173",
            },
        )
        anonymous_csrf = client.cookies.get(auth_settings.effective_csrf_cookie_name)
        assert anonymous_csrf is not None
        second = await client.post(
            "/api/v1/auth/logout",
            headers={
                auth_settings.csrf_header_name: anonymous_csrf,
                "Origin": "http://localhost:5173",
            },
        )

    assert first.status_code == 204
    assert first.content == b""
    assert second.status_code == 204
    assert second.content == b""
    if user_id is not None and session_id is not None:
        record = {item.id: item for item in session_records(auth_engine, user_id)}[
            session_id
        ]
        if session_state == "expired":
            assert record.revoked_at is None
        else:
            assert record.revoked_at is not None


@pytest.mark.anyio
async def test_logout_csrf_failure_does_not_revoke_session(
    auth_engine: Engine,
    auth_settings: Settings,
) -> None:
    user_id = create_user(auth_engine, email=unique_email())
    session_id, raw_token = create_persisted_session(
        auth_engine,
        auth_settings,
        user_id,
    )
    app = build_auth_app(auth_engine, auth_settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        set_browser_session_cookie(
            client,
            auth_settings.effective_session_cookie_name,
            raw_token,
        )
        missing = await client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://localhost:5173"},
        )
        token = await bootstrap_csrf(client)
        invalid_origin = await client.post(
            "/api/v1/auth/logout",
            headers={
                auth_settings.csrf_header_name: token,
                "Origin": "https://attacker.example",
            },
        )

    assert missing.status_code == 403
    assert invalid_origin.status_code == 403
    assert missing.json() == CSRF_FAILURE_DETAIL
    assert invalid_origin.json() == CSRF_FAILURE_DETAIL
    record = {item.id: item for item in session_records(auth_engine, user_id)}[
        session_id
    ]
    assert record.revoked_at is None


@pytest.mark.anyio
async def test_logout_database_failure_rolls_back_without_clearing_cookie(
    auth_engine: Engine,
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = create_user(auth_engine, email=unique_email())
    session_id, raw_token = create_persisted_session(
        auth_engine,
        auth_settings,
        user_id,
    )
    app = build_auth_app(auth_engine, auth_settings)

    def fail_commit(self: DbSession) -> NoReturn:
        raise RuntimeError("controlled logout commit failure")

    monkeypatch.setattr(DbSession, "commit", fail_commit)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        set_browser_session_cookie(
            client,
            auth_settings.effective_session_cookie_name,
            raw_token,
        )
        csrf_token = await bootstrap_csrf(client)
        response = await client.post(
            "/api/v1/auth/logout",
            headers={
                auth_settings.csrf_header_name: csrf_token,
                "Origin": "http://localhost:5173",
            },
        )

    assert response.status_code == 500
    assert response.headers.get_list("set-cookie") == []
    record = {item.id: item for item in session_records(auth_engine, user_id)}[
        session_id
    ]
    assert record.revoked_at is None


def test_login_request_masks_password_in_repr() -> None:
    from app.auth.schemas import LoginRequest

    request = LoginRequest.model_validate(
        {"email": "person@example.com", "password": VALID_PASSWORD}
    )

    assert VALID_PASSWORD not in repr(request)
    assert request.password.get_secret_value() == VALID_PASSWORD
