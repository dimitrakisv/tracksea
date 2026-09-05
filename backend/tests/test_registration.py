from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier
from typing import NoReturn
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import AnyHttpUrl, SecretStr
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

import app.auth.service as auth_service
from app.auth.csrf import CsrfValidationError, validate_csrf_token
from app.auth.models import Session
from app.auth.passwords import verify_password
from app.auth.schemas import RegistrationRequest
from app.auth.service import AccountConflictError, register_user
from app.auth.sessions import hash_session_token
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, get_db_session
from app.main import create_app
from app.users.models import ExternalIdentity, User
from app.users.service import MAX_DISPLAY_NAME_LENGTH

TEST_EMAIL_PREFIX = "step9-registration-"
VALID_PASSWORD = "a private ocean passphrase"
TEST_CSRF_SECRET = SecretStr("test-csrf-secret-with-at-least-32-bytes")
CONFLICT_DETAIL = {
    "code": "account_conflict",
    "message": "An account cannot be created with these details.",
}


@dataclass(frozen=True, slots=True)
class RegistrationHttpResult:
    bootstrap_token: str
    response: httpx.Response
    session_token: str | None
    csrf_token: str | None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def registration_settings() -> Settings:
    return Settings()


@pytest.fixture
def registration_engine(
    registration_settings: Settings,
) -> Generator[Engine, None, None]:
    url = make_url(registration_settings.database_url)
    if url.host not in {"127.0.0.1", "localhost", "postgres"}:
        pytest.fail("Registration tests require a local PostgreSQL database.")

    engine = create_db_engine(registration_settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.fail("Local PostgreSQL must be available for registration tests.")

    yield engine

    with DbSession(engine) as db:
        db.execute(
            delete(User).where(User.normalized_email.like(f"{TEST_EMAIL_PREFIX}%"))
        )
        db.commit()
    engine.dispose()


def build_registration_app(engine: Engine, settings: Settings) -> FastAPI:
    app = create_app()

    def database_override() -> Generator[DbSession, None, None]:
        with DbSession(engine, expire_on_commit=False) as db:
            yield db

    async def settings_override() -> Settings:
        return settings

    app.dependency_overrides[get_db_session] = database_override
    app.dependency_overrides[get_settings] = settings_override
    return app


def registration_payload(
    email: str,
    *,
    password: str = VALID_PASSWORD,
    display_name: str = "Marine Observer",
) -> dict[str, str]:
    return {
        "email": email,
        "password": password,
        "display_name": display_name,
    }


async def post_registration(
    app: FastAPI,
    settings: Settings,
    payload: dict[str, str],
    *,
    origin: str | None = None,
    incoming_session: str | None = None,
    raise_app_exceptions: bool = True,
) -> RegistrationHttpResult:
    transport = httpx.ASGITransport(
        app=app,
        raise_app_exceptions=raise_app_exceptions,
    )
    base_url = (
        "https://testserver" if settings.session_cookie_secure else "http://testserver"
    )
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        if incoming_session is not None:
            client.cookies.set(
                settings.effective_session_cookie_name,
                incoming_session,
            )
        bootstrap = await client.get("/api/v1/auth/csrf")
        assert bootstrap.status_code == 200
        bootstrap_token = bootstrap.json()["csrf_token"]
        response = await client.post(
            "/api/v1/auth/register",
            json=payload,
            headers={
                settings.csrf_header_name: bootstrap_token,
                "Origin": origin or str(settings.frontend_origin).rstrip("/"),
            },
        )
        session_token = response.cookies.get(settings.effective_session_cookie_name)
        csrf_token = response.cookies.get(settings.effective_csrf_cookie_name)

    return RegistrationHttpResult(
        bootstrap_token=bootstrap_token,
        response=response,
        session_token=session_token,
        csrf_token=csrf_token,
    )


def user_by_normalized_email(engine: Engine, normalized_email: str) -> User | None:
    with DbSession(engine) as db:
        return db.scalar(select(User).where(User.normalized_email == normalized_email))


def user_counts(engine: Engine, normalized_email: str) -> tuple[int, int, int]:
    with DbSession(engine) as db:
        user_ids = select(User.id).where(User.normalized_email == normalized_email)
        users = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.normalized_email == normalized_email)
        )
        sessions = db.scalar(
            select(func.count())
            .select_from(Session)
            .where(Session.user_id.in_(user_ids))
        )
        identities = db.scalar(
            select(func.count())
            .select_from(ExternalIdentity)
            .where(ExternalIdentity.user_id.in_(user_ids))
        )
    assert users is not None
    assert sessions is not None
    assert identities is not None
    return users, sessions, identities


def get_only_session(engine: Engine, user_id: object) -> Session:
    with DbSession(engine) as db:
        records = list(db.scalars(select(Session).where(Session.user_id == user_id)))
        assert len(records) == 1
        db.expunge(records[0])
        return records[0]


def cookie_header(response: httpx.Response, name: str) -> str:
    return next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{name}=")
    )


@pytest.mark.anyio
async def test_successful_registration_is_safe_atomic_and_session_bound(
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    suffix = uuid4().hex
    canonical_email = f"Step9-Registration-{suffix}+tag@example.com"
    email = f" Step9-Registration-{suffix}+tag@EXAMPLE.COM "
    normalized_email = f"{TEST_EMAIL_PREFIX}{suffix}+tag@example.com"
    password = "  μια ασφαλής θαλάσσια φράση  "
    display_name = "  Θαλάσσια Παρατηρήτρια  "
    app = build_registration_app(registration_engine, registration_settings)

    result = await post_registration(
        app,
        registration_settings,
        registration_payload(
            email,
            password=password,
            display_name=display_name,
        ),
    )

    assert result.response.status_code == 201, result.response.text
    body = result.response.json()
    assert set(body) == {
        "id",
        "email",
        "email_verified",
        "display_name",
        "authentication_methods",
    }
    assert body["email"] == canonical_email
    assert body["email_verified"] is False
    assert body["display_name"] == "Θαλάσσια Παρατηρήτρια"
    assert body["authentication_methods"] == ["password"]
    serialized = result.response.text
    for secret in (
        password,
        VALID_PASSWORD,
        TEST_CSRF_SECRET.get_secret_value(),
    ):
        assert secret not in serialized
    for private_field in (
        "normalized_email",
        "password_hash",
        "token_hash",
        "session_id",
        "csrf_secret",
    ):
        assert private_field not in body

    user = user_by_normalized_email(registration_engine, normalized_email)
    assert user is not None
    assert user.email == canonical_email
    assert user.normalized_email == normalized_email
    assert user.display_name == "Θαλάσσια Παρατηρήτρια"
    assert user.email_verified_at is None
    assert user.is_active
    assert user.password_hash is not None
    assert user.password_hash != password
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(password, user.password_hash)
    assert user_counts(registration_engine, normalized_email) == (1, 1, 0)

    assert result.session_token is not None
    assert result.csrf_token is not None
    session = get_only_session(registration_engine, user.id)
    assert len(session.token_hash) == 32
    assert session.token_hash == hash_session_token(result.session_token)
    assert session.token_hash != result.session_token.encode()
    assert not hasattr(session, "raw_token")
    assert session.expires_at > session.created_at
    validate_csrf_token(
        result.csrf_token,
        settings=registration_settings,
        session_token=result.session_token,
    )
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(
            result.csrf_token,
            settings=registration_settings,
            session_token="a-different-session-token",
        )
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(
            result.bootstrap_token,
            settings=registration_settings,
            session_token=result.session_token,
        )

    session_cookie = cookie_header(
        result.response,
        registration_settings.effective_session_cookie_name,
    )
    csrf_cookie = cookie_header(
        result.response,
        registration_settings.effective_csrf_cookie_name,
    )
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert f"Max-Age={registration_settings.session_lifetime_seconds}" in session_cookie
    assert "Path=/" in session_cookie
    assert "Secure" not in session_cookie
    assert "Domain=" not in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert f"Max-Age={registration_settings.csrf_token_ttl_seconds}" in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "Secure" not in csrf_cookie
    assert "Domain=" not in csrf_cookie


@pytest.mark.anyio
async def test_registration_uses_secure_host_cookies_outside_local_http(
    registration_engine: Engine,
) -> None:
    settings = Settings(
        environment="production",
        frontend_origin=AnyHttpUrl("https://tracksea.example"),
        csrf_secret=TEST_CSRF_SECRET,
        session_cookie_secure=True,
        session_cookie_name=None,
        csrf_cookie_name=None,
    )
    app = build_registration_app(registration_engine, settings)
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"

    result = await post_registration(
        app,
        settings,
        registration_payload(email),
        origin="https://tracksea.example",
    )

    assert result.response.status_code == 201, result.response.text
    session_cookie = cookie_header(
        result.response,
        settings.effective_session_cookie_name,
    )
    csrf_cookie = cookie_header(
        result.response,
        settings.effective_csrf_cookie_name,
    )
    assert session_cookie.startswith("__Host-tracksea_session=")
    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "Domain=" not in session_cookie
    assert csrf_cookie.startswith("__Host-tracksea_csrf=")
    assert "HttpOnly" not in csrf_cookie
    assert "Secure" in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "Domain=" not in csrf_cookie


@pytest.mark.anyio
async def test_registration_does_not_reuse_an_incoming_session_cookie(
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    incoming = "browser-controlled-session-token"
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    app = build_registration_app(registration_engine, registration_settings)

    result = await post_registration(
        app,
        registration_settings,
        registration_payload(email),
        incoming_session=incoming,
    )

    assert result.response.status_code == 201
    assert result.session_token is not None
    assert result.session_token != incoming
    user = user_by_normalized_email(registration_engine, email)
    assert user is not None
    session = get_only_session(registration_engine, user.id)
    assert session.token_hash != hash_session_token(incoming)


@pytest.mark.anyio
async def test_registration_requires_valid_csrf_and_origin(
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    app = build_registration_app(registration_engine, registration_settings)
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        missing_csrf = await client.post(
            "/api/v1/auth/register",
            json=registration_payload(email),
            headers={"Origin": "http://localhost:5173"},
        )
        bootstrap = await client.get("/api/v1/auth/csrf")
        token = bootstrap.json()["csrf_token"]
        wrong_origin = await client.post(
            "/api/v1/auth/register",
            json=registration_payload(email),
            headers={
                registration_settings.csrf_header_name: token,
                "Origin": "http://localhost:5173.evil.example",
            },
        )

    for response in (missing_csrf, wrong_origin):
        assert response.status_code == 403
        assert response.json() == {
            "detail": {
                "code": "csrf_failed",
                "message": "Request could not be verified.",
            }
        }
    assert user_counts(registration_engine, email) == (0, 0, 0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "not-an-email"),
        ("password", "x" * 14),
        ("password", "x" * 129),
        ("password", "Mailcreated5240"),
        ("password", "TrackSea-Password"),
        ("display_name", "   \t\n  "),
        ("display_name", "x" * (MAX_DISPLAY_NAME_LENGTH + 1)),
    ],
)
@pytest.mark.anyio
async def test_registration_validation_is_safe(
    field: str,
    value: str,
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    payload = registration_payload(email)
    payload[field] = value
    app = build_registration_app(registration_engine, registration_settings)

    result = await post_registration(app, registration_settings, payload)

    assert result.response.status_code == 422
    if field == "password":
        assert value not in result.response.text
    assert VALID_PASSWORD not in result.response.text
    assert result.session_token is None
    assert user_counts(registration_engine, email) == (0, 0, 0)


@pytest.mark.anyio
async def test_registration_rejects_unexpected_fields(
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    payload = registration_payload(email)
    payload["is_active"] = "false"
    app = build_registration_app(registration_engine, registration_settings)

    result = await post_registration(app, registration_settings, payload)

    assert result.response.status_code == 422
    assert result.session_token is None
    assert user_counts(registration_engine, email) == (0, 0, 0)


@pytest.mark.anyio
async def test_display_name_minimum_unicode_trim_and_duplicates(
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    app = build_registration_app(registration_engine, registration_settings)
    first_email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    second_email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    third_email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"

    first = await post_registration(
        app,
        registration_settings,
        registration_payload(first_email, display_name="  Θ  "),
    )
    second = await post_registration(
        app,
        registration_settings,
        registration_payload(second_email, display_name="Θ"),
    )
    maximum = await post_registration(
        app,
        registration_settings,
        registration_payload(
            third_email,
            display_name="Θ" * MAX_DISPLAY_NAME_LENGTH,
        ),
    )

    assert first.response.status_code == 201
    assert second.response.status_code == 201
    assert maximum.response.status_code == 201
    assert first.response.json()["display_name"] == "Θ"
    assert second.response.json()["display_name"] == "Θ"
    assert maximum.response.json()["display_name"] == "Θ" * MAX_DISPLAY_NAME_LENGTH


@pytest.mark.anyio
async def test_provider_alias_like_emails_remain_distinct(
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    suffix = uuid4().hex
    first_email = f"{TEST_EMAIL_PREFIX}{suffix}+first@gmail.com"
    second_email = f"{TEST_EMAIL_PREFIX}{suffix}+second@gmail.com"
    app = build_registration_app(registration_engine, registration_settings)

    first = await post_registration(
        app,
        registration_settings,
        registration_payload(first_email),
    )
    second = await post_registration(
        app,
        registration_settings,
        registration_payload(second_email),
    )

    assert first.response.status_code == 201
    assert second.response.status_code == 201
    assert user_counts(registration_engine, first_email) == (1, 1, 0)
    assert user_counts(registration_engine, second_email) == (1, 1, 0)


@pytest.mark.parametrize("duplicate_kind", ["exact", "case_insensitive"])
@pytest.mark.anyio
async def test_duplicate_email_returns_generic_conflict(
    duplicate_kind: str,
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    suffix = uuid4().hex
    canonical_email = f"{TEST_EMAIL_PREFIX}{suffix}@example.com"
    duplicate_email = (
        canonical_email
        if duplicate_kind == "exact"
        else f"{TEST_EMAIL_PREFIX.upper()}{suffix.upper()}@EXAMPLE.COM"
    )
    app = build_registration_app(registration_engine, registration_settings)

    first = await post_registration(
        app,
        registration_settings,
        registration_payload(canonical_email),
    )
    duplicate = await post_registration(
        app,
        registration_settings,
        registration_payload(duplicate_email),
    )

    assert first.response.status_code == 201
    assert duplicate.response.status_code == 409
    assert duplicate.response.json() == {"detail": CONFLICT_DETAIL}
    assert duplicate.session_token is None
    assert "password" not in duplicate.response.text.casefold()
    assert "google" not in duplicate.response.text.casefold()
    assert canonical_email not in duplicate.response.text
    assert user_counts(registration_engine, canonical_email) == (1, 1, 0)


def test_database_constraint_resolves_concurrent_registration_race(
    registration_engine: Engine,
    registration_settings: Settings,
) -> None:
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    request = RegistrationRequest.model_validate(registration_payload(email))
    barrier = Barrier(2)

    def attempt_registration() -> str:
        with DbSession(registration_engine, expire_on_commit=False) as db:
            barrier.wait()
            try:
                register_user(db, request, settings=registration_settings)
            except AccountConflictError:
                return "conflict"
            return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt_registration(), range(2)))

    assert sorted(outcomes) == ["conflict", "created"]
    assert user_counts(registration_engine, email) == (1, 1, 0)


@pytest.mark.anyio
async def test_session_creation_failure_rolls_back_without_setting_session_cookie(
    registration_engine: Engine,
    registration_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    app = build_registration_app(registration_engine, registration_settings)

    def fail_session_creation(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("controlled session creation failure")

    monkeypatch.setattr(auth_service, "create_session", fail_session_creation)

    result = await post_registration(
        app,
        registration_settings,
        registration_payload(email),
        raise_app_exceptions=False,
    )

    assert result.response.status_code == 500
    assert result.session_token is None
    assert registration_settings.effective_session_cookie_name not in "".join(
        result.response.headers.get_list("set-cookie")
    )
    assert VALID_PASSWORD not in result.response.text
    assert user_counts(registration_engine, email) == (0, 0, 0)


def test_registration_request_masks_password_in_repr() -> None:
    request = RegistrationRequest.model_validate(
        registration_payload("person@example.com", password=VALID_PASSWORD)
    )

    assert VALID_PASSWORD not in repr(request)
    assert request.password.get_secret_value() == VALID_PASSWORD
