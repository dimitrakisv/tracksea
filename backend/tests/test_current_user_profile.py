from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

from app.auth.csrf import issue_csrf_token
from app.auth.models import AuthThrottleBucket, Session
from app.auth.passwords import hash_password
from app.auth.sessions import generate_session_token, hash_session_token
from app.auth.throttling import build_login_throttle_keys, record_login_failure
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, get_db_session
from app.main import create_app
from app.users.email import normalize_email
from app.users.models import ExternalIdentity, User
from app.users.service import update_current_user_display_name

TEST_EMAIL_PREFIX = "step12-profile-"
VALID_PASSWORD = "a private ocean passphrase"
SAFE_FIELDS = {
    "id",
    "email",
    "email_verified",
    "display_name",
    "authentication_methods",
}
AUTHENTICATION_REQUIRED = {
    "detail": {
        "code": "authentication_required",
        "message": "Authentication is required.",
    }
}
CSRF_FAILED = {
    "detail": {
        "code": "csrf_failed",
        "message": "Request could not be verified.",
    }
}


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    user_id: UUID
    email: str
    session_id: UUID
    raw_session_token: str
    expires_at: datetime
    last_seen_at: datetime


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def profile_settings() -> Settings:
    return Settings(
        csrf_secret=SecretStr(f"step12-csrf-secret-{uuid4().hex}"),
        auth_throttle_secret=SecretStr(f"step12-throttle-secret-{uuid4().hex}"),
    )


@pytest.fixture
def profile_engine(profile_settings: Settings) -> Generator[Engine, None, None]:
    url = make_url(profile_settings.database_url)
    if url.host not in {"127.0.0.1", "localhost", "postgres"}:
        pytest.fail("Profile tests require a local PostgreSQL database.")

    engine = create_db_engine(profile_settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.fail("Local PostgreSQL must be available for profile tests.")

    with DbSession(engine) as db:
        baseline_throttle_ids = set(db.scalars(select(AuthThrottleBucket.id)))

    yield engine

    with DbSession(engine) as db:
        db.execute(
            delete(User).where(User.normalized_email.like(f"{TEST_EMAIL_PREFIX}%"))
        )
        cleanup = delete(AuthThrottleBucket)
        if baseline_throttle_ids:
            cleanup = cleanup.where(AuthThrottleBucket.id.not_in(baseline_throttle_ids))
        db.execute(cleanup)
        db.commit()
    engine.dispose()


@pytest.fixture
def profile_app(profile_engine: Engine, profile_settings: Settings) -> FastAPI:
    app = create_app()

    def database_override() -> Generator[DbSession, None, None]:
        with DbSession(profile_engine, expire_on_commit=False) as db:
            yield db

    async def settings_override() -> Settings:
        return profile_settings

    app.dependency_overrides[get_db_session] = database_override
    app.dependency_overrides[get_settings] = settings_override
    return app


def create_profile_record(
    engine: Engine,
    *,
    display_name: str = "Marine Observer",
    active: bool = True,
    verified: bool = False,
    google_identity: bool = False,
    expires_at: datetime | None = None,
    revoked: bool = False,
) -> ProfileRecord:
    now = datetime.now(UTC)
    suffix = uuid4().hex
    email = f"{TEST_EMAIL_PREFIX}{suffix}@Example.com"
    normalized = normalize_email(email)
    raw_token = generate_session_token()
    selected_expiry = expires_at or now + timedelta(hours=1)
    last_seen_at = now

    with DbSession(engine, expire_on_commit=False) as db:
        user = User(
            email=normalized.canonical,
            normalized_email=normalized.normalized,
            display_name=display_name,
            password_hash=hash_password(VALID_PASSWORD),
            email_verified_at=now if verified else None,
            is_active=active,
        )
        db.add(user)
        db.flush()
        if google_identity:
            db.add(
                ExternalIdentity(
                    user_id=user.id,
                    provider="google",
                    subject=f"google-{suffix}",
                    email_snapshot=user.email,
                )
            )
        session = Session(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            created_at=min(
                now - timedelta(minutes=1), selected_expiry - timedelta(hours=1)
            ),
            expires_at=selected_expiry,
            last_seen_at=last_seen_at,
            revoked_at=now if revoked else None,
        )
        db.add(session)
        db.flush()
        result = ProfileRecord(
            user_id=user.id,
            email=user.email,
            session_id=session.id,
            raw_session_token=raw_token,
            expires_at=selected_expiry,
            last_seen_at=last_seen_at,
        )
        db.commit()
    return result


def authenticated_client(
    app: FastAPI,
    settings: Settings,
    raw_session_token: str,
) -> httpx.AsyncClient:
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    client.cookies.set(settings.effective_session_cookie_name, raw_session_token)
    return client


async def session_csrf(client: httpx.AsyncClient) -> str:
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def patch_headers(settings: Settings, csrf_token: str) -> dict[str, str]:
    return {
        settings.csrf_header_name: csrf_token,
        "Origin": str(settings.frontend_origin).rstrip("/"),
    }


def load_user(engine: Engine, user_id: UUID) -> User:
    with DbSession(engine) as db:
        user = db.get(User, user_id)
        assert user is not None
        db.expunge(user)
    return user


def load_session(engine: Engine, session_id: UUID) -> Session:
    with DbSession(engine) as db:
        session = db.get(Session, session_id)
        assert session is not None
        db.expunge(session)
    return session


def count_sessions(engine: Engine, user_id: UUID) -> int:
    with DbSession(engine) as db:
        count = db.scalar(
            select(func.count()).select_from(Session).where(Session.user_id == user_id)
        )
    assert count is not None
    return count


@pytest.mark.anyio
async def test_get_me_returns_exact_safe_persisted_profile_without_csrf(
    profile_app: FastAPI,
    profile_engine: Engine,
    profile_settings: Settings,
) -> None:
    record = create_profile_record(
        profile_engine,
        verified=True,
        google_identity=True,
    )

    async with authenticated_client(
        profile_app,
        profile_settings,
        record.raw_session_token,
    ) as client:
        assert profile_settings.effective_csrf_cookie_name not in client.cookies
        response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert set(response.json()) == SAFE_FIELDS
    assert response.json() == {
        "id": str(record.user_id),
        "email": record.email,
        "email_verified": True,
        "display_name": "Marine Observer",
        "authentication_methods": ["password", "google"],
    }
    assert response.headers["cache-control"] == "no-store"
    serialized = response.text.casefold()
    for forbidden in (
        "normalized_email",
        "password_hash",
        "subject",
        "session",
        "token",
        "expires",
        "revoked",
        "throttle",
        "failure_count",
        "key_hash",
        "created_at",
    ):
        assert forbidden not in serialized


@pytest.mark.anyio
@pytest.mark.parametrize(
    "session_kind", ["missing", "unknown", "expired", "revoked", "inactive"]
)
async def test_get_me_uses_one_generic_error_for_unavailable_authentication(
    session_kind: str,
    profile_app: FastAPI,
    profile_engine: Engine,
    profile_settings: Settings,
) -> None:
    raw_token: str | None = None
    if session_kind == "unknown":
        raw_token = generate_session_token()
    elif session_kind != "missing":
        record = create_profile_record(
            profile_engine,
            active=session_kind != "inactive",
            expires_at=(
                datetime.now(UTC) - timedelta(minutes=1)
                if session_kind == "expired"
                else None
            ),
            revoked=session_kind == "revoked",
        )
        raw_token = record.raw_session_token

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=profile_app),
        base_url="http://testserver",
    ) as client:
        if raw_token is not None:
            client.cookies.set(
                profile_settings.effective_session_cookie_name, raw_token
            )
        response = await client.get(
            "/api/v1/auth/me?user_id=browser-controlled",
            headers={
                "Authorization": "Bearer unsupported-token",
                "X-User-ID": str(uuid4()),
            },
        )

    assert response.status_code == 401
    assert response.json() == AUTHENTICATION_REQUIRED
    assert "expired" not in response.text
    assert "revoked" not in response.text
    assert "inactive" not in response.text


@pytest.mark.anyio
async def test_patch_updates_only_current_user_and_preserves_security_state(
    profile_app: FastAPI,
    profile_engine: Engine,
    profile_settings: Settings,
) -> None:
    record = create_profile_record(profile_engine, google_identity=True)
    other = create_profile_record(profile_engine, display_name="Other Observer")
    throttle_keys = build_login_throttle_keys(
        normalize_email(record.email).normalized,
        "127.0.0.1",
        settings=profile_settings,
    )
    with DbSession(profile_engine) as db:
        record_login_failure(db, throttle_keys, settings=profile_settings)
        db.commit()
    before_session = load_session(profile_engine, record.session_id)

    async with authenticated_client(
        profile_app,
        profile_settings,
        record.raw_session_token,
    ) as client:
        csrf_token = await session_csrf(client)
        session_cookie_before = client.cookies[
            profile_settings.effective_session_cookie_name
        ]
        csrf_cookie_before = client.cookies[profile_settings.effective_csrf_cookie_name]
        response = await client.patch(
            f"/api/v1/users/me?user_id={other.user_id}",
            json={"display_name": "  Θαλάσσια Παρατηρήτρια  "},
            headers={
                **patch_headers(profile_settings, csrf_token),
                "X-User-ID": str(other.user_id),
            },
        )
        subsequent = await client.get("/api/v1/auth/me")
        session_cookie_after = client.cookies[
            profile_settings.effective_session_cookie_name
        ]
        csrf_cookie_after = client.cookies[profile_settings.effective_csrf_cookie_name]

    assert response.status_code == 200
    assert set(response.json()) == SAFE_FIELDS
    assert response.json()["id"] == str(record.user_id)
    assert response.json()["email"] == record.email
    assert response.json()["display_name"] == "Θαλάσσια Παρατηρήτρια"
    assert response.json()["authentication_methods"] == ["password", "google"]
    assert subsequent.status_code == 200
    assert subsequent.json()["display_name"] == "Θαλάσσια Παρατηρήτρια"
    assert (
        load_user(profile_engine, record.user_id).display_name
        == "Θαλάσσια Παρατηρήτρια"
    )
    assert load_user(profile_engine, other.user_id).display_name == "Other Observer"
    assert session_cookie_after == session_cookie_before == record.raw_session_token
    assert csrf_cookie_after == csrf_cookie_before == csrf_token
    assert response.headers.get_list("set-cookie") == []
    assert count_sessions(profile_engine, record.user_id) == 1
    after_session = load_session(profile_engine, record.session_id)
    assert after_session.expires_at == before_session.expires_at == record.expires_at
    assert after_session.revoked_at == before_session.revoked_at is None
    assert after_session.last_seen_at == before_session.last_seen_at
    with DbSession(profile_engine) as db:
        buckets = list(
            db.scalars(
                select(AuthThrottleBucket).where(
                    AuthThrottleBucket.key_hash.in_(
                        [throttle_keys.account, throttle_keys.ip]
                    )
                )
            )
        )
    assert {row.scope: row.failure_count for row in buckets} == {
        "account": 1,
        "ip": 1,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("display_name", ["Z", "Θ" * 80])
async def test_patch_accepts_display_name_boundaries(
    display_name: str,
    profile_app: FastAPI,
    profile_engine: Engine,
    profile_settings: Settings,
) -> None:
    record = create_profile_record(profile_engine)
    async with authenticated_client(
        profile_app,
        profile_settings,
        record.raw_session_token,
    ) as client:
        csrf_token = await session_csrf(client)
        response = await client.patch(
            "/api/v1/users/me",
            json={"display_name": display_name},
            headers=patch_headers(profile_settings, csrf_token),
        )

    assert response.status_code == 200
    assert response.json()["display_name"] == display_name
    assert response.json()["authentication_methods"] == ["password"]
    assert load_user(profile_engine, record.user_id).display_name == display_name


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": "   "},
        {"display_name": "x" * 81},
        {"display_name": "Changed", "email": "attacker@example.com"},
        {"display_name": "Changed", "password": "replacement password"},
        {"display_name": "Changed", "is_active": False},
        {"display_name": "Changed", "id": "00000000-0000-0000-0000-000000000000"},
        {"display_name": "Changed", "normalized_email": "attacker@example.com"},
        {"display_name": "Changed", "authentication_methods": ["google"]},
    ],
)
async def test_patch_rejects_invalid_or_disallowed_fields_without_changes(
    payload: dict[str, object],
    profile_app: FastAPI,
    profile_engine: Engine,
    profile_settings: Settings,
) -> None:
    record = create_profile_record(profile_engine)
    before = load_user(profile_engine, record.user_id)
    async with authenticated_client(
        profile_app,
        profile_settings,
        record.raw_session_token,
    ) as client:
        csrf_token = await session_csrf(client)
        response = await client.patch(
            "/api/v1/users/me",
            json=payload,
            headers=patch_headers(profile_settings, csrf_token),
        )

    assert response.status_code == 422
    after = load_user(profile_engine, record.user_id)
    assert after.display_name == before.display_name
    assert after.email == before.email
    assert after.normalized_email == before.normalized_email
    assert after.password_hash == before.password_hash
    assert after.is_active == before.is_active


@pytest.mark.anyio
@pytest.mark.parametrize(
    "csrf_case",
    ["missing_header", "missing_cookie", "mismatch", "invalid_origin"],
)
async def test_patch_requires_valid_session_bound_csrf(
    csrf_case: str,
    profile_app: FastAPI,
    profile_engine: Engine,
    profile_settings: Settings,
) -> None:
    record = create_profile_record(profile_engine)
    async with authenticated_client(
        profile_app,
        profile_settings,
        record.raw_session_token,
    ) as client:
        csrf_token = await session_csrf(client)
        headers = patch_headers(profile_settings, csrf_token)
        if csrf_case == "missing_header":
            headers.pop(profile_settings.csrf_header_name)
        elif csrf_case == "missing_cookie":
            client.cookies.delete(profile_settings.effective_csrf_cookie_name)
        elif csrf_case == "mismatch":
            headers[profile_settings.csrf_header_name] = issue_csrf_token(
                settings=profile_settings,
                session_token=record.raw_session_token,
            )
        else:
            headers["Origin"] = "https://attacker.example"

        response = await client.patch(
            "/api/v1/users/me",
            json={"display_name": "Must Not Persist"},
            headers=headers,
        )

    assert response.status_code == 403
    assert response.json() == CSRF_FAILED
    assert load_user(profile_engine, record.user_id).display_name == "Marine Observer"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "session_kind", ["anonymous", "expired", "revoked", "inactive"]
)
async def test_patch_uses_generic_authentication_failure(
    session_kind: str,
    profile_app: FastAPI,
    profile_engine: Engine,
    profile_settings: Settings,
) -> None:
    raw_token: str | None = None
    if session_kind != "anonymous":
        record = create_profile_record(
            profile_engine,
            active=session_kind != "inactive",
            expires_at=(
                datetime.now(UTC) - timedelta(minutes=1)
                if session_kind == "expired"
                else None
            ),
            revoked=session_kind == "revoked",
        )
        raw_token = record.raw_session_token

    csrf_token = issue_csrf_token(
        settings=profile_settings,
        session_token=raw_token,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=profile_app),
        base_url="http://testserver",
    ) as client:
        if raw_token is not None:
            client.cookies.set(
                profile_settings.effective_session_cookie_name, raw_token
            )
        client.cookies.set(profile_settings.effective_csrf_cookie_name, csrf_token)
        response = await client.patch(
            "/api/v1/users/me",
            json={"display_name": "Must Not Persist"},
            headers=patch_headers(profile_settings, csrf_token),
        )

    assert response.status_code == 401
    assert response.json() == AUTHENTICATION_REQUIRED
    assert "expired" not in response.text
    assert "revoked" not in response.text
    assert "inactive" not in response.text


def test_profile_update_rolls_back_when_commit_fails(
    profile_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = create_profile_record(profile_engine)
    with DbSession(profile_engine) as db:
        original_commit = db.commit

        def fail_commit() -> None:
            raise RuntimeError("controlled profile commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="controlled profile commit failure"):
            update_current_user_display_name(db, record.user_id, "Must Roll Back")
        monkeypatch.setattr(db, "commit", original_commit)

    assert load_user(profile_engine, record.user_id).display_name == "Marine Observer"
