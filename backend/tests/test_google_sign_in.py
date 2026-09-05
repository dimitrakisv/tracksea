from __future__ import annotations

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import NoReturn
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

import app.auth.service as auth_service
from app.auth.csrf import CsrfValidationError, validate_csrf_token
from app.auth.dependencies import get_google_credential_verifier
from app.auth.google import (
    GoogleCredentialVerificationError,
    VerifiedGoogleIdentity,
)
from app.auth.models import AuthThrottleBucket, Session
from app.auth.passwords import hash_password
from app.auth.schemas import GoogleSignInRequest
from app.auth.service import GoogleAccountLinkRequiredError, google_sign_in
from app.auth.sessions import create_session, hash_session_token
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, get_db_session
from app.main import create_app
from app.users.email import normalize_email
from app.users.models import ExternalIdentity, User

TEST_EMAIL_PREFIX = "step14-google-"
TEST_SUBJECT_PREFIX = "step14-subject-"
CREDENTIAL = "candidate-google-credential-must-remain-private"
INVALID_CREDENTIALS_DETAIL = {
    "detail": {
        "code": "invalid_credentials",
        "message": "Google sign-in could not be completed.",
    }
}
LINK_REQUIRED_DETAIL = {
    "detail": {
        "code": "account_link_required",
        "message": "Sign in to the existing account before linking Google.",
    }
}
CSRF_FAILURE_DETAIL = {
    "detail": {
        "code": "csrf_failed",
        "message": "Request could not be verified.",
    }
}


class FakeGoogleVerifier:
    def __init__(
        self,
        result: VerifiedGoogleIdentity | Exception,
        *,
        barrier: Barrier | None = None,
    ) -> None:
        self.result = result
        self.barrier = barrier
        self.calls = 0

    def verify(self, credential: str) -> VerifiedGoogleIdentity:
        self.calls += 1
        if self.barrier is not None:
            self.barrier.wait(timeout=10)
        if isinstance(self.result, Exception):
            raise self.result
        assert credential
        return self.result


@dataclass(frozen=True, slots=True)
class GoogleHttpResult:
    bootstrap_token: str
    response: httpx.Response
    session_token: str | None
    csrf_token: str | None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def google_settings() -> Settings:
    return Settings(google_client_id="tracksea-test.apps.googleusercontent.com")


@pytest.fixture
def google_engine(google_settings: Settings) -> Generator[Engine, None, None]:
    url = make_url(google_settings.database_url)
    if url.host not in {"127.0.0.1", "localhost", "postgres"}:
        pytest.fail("Google sign-in tests require a local PostgreSQL database.")

    engine = create_db_engine(google_settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.fail("Local PostgreSQL must be available for Google sign-in tests.")

    yield engine

    with DbSession(engine) as db:
        db.execute(
            delete(User).where(User.normalized_email.like(f"{TEST_EMAIL_PREFIX}%"))
        )
        db.commit()
    engine.dispose()


def verified_identity(
    *,
    subject: str | None = None,
    email: str | None = None,
    email_verified: bool = True,
    name: str | None = "Marine Scientist",
    picture: str | None = "https://example.com/private-provider-picture.jpg",
) -> VerifiedGoogleIdentity:
    suffix = uuid4().hex
    return VerifiedGoogleIdentity(
        subject=subject or f"{TEST_SUBJECT_PREFIX}{suffix}",
        email=email or f"{TEST_EMAIL_PREFIX}{suffix}@example.com",
        email_verified=email_verified,
        name=name,
        picture=picture,
    )


def build_google_app(
    engine: Engine,
    settings: Settings,
    verifier: FakeGoogleVerifier | None,
) -> FastAPI:
    app = create_app()

    def database_override() -> Generator[DbSession, None, None]:
        with DbSession(engine, expire_on_commit=False) as db:
            yield db

    async def settings_override() -> Settings:
        return settings

    app.dependency_overrides[get_db_session] = database_override
    app.dependency_overrides[get_settings] = settings_override
    if verifier is not None:
        app.dependency_overrides[get_google_credential_verifier] = lambda: verifier
    return app


async def post_google(
    app: FastAPI,
    settings: Settings,
    *,
    payload: object | None = None,
    incoming_session: str | None = None,
    origin: str | None = None,
    csrf_header: str | None = None,
    omit_csrf_header: bool = False,
    raise_app_exceptions: bool = True,
) -> GoogleHttpResult:
    transport = httpx.ASGITransport(
        app=app,
        raise_app_exceptions=raise_app_exceptions,
    )
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        if incoming_session is not None:
            client.cookies.set(
                settings.effective_session_cookie_name,
                incoming_session,
                domain="testserver.local",
                path="/",
            )
        bootstrap = await client.get("/api/v1/auth/csrf")
        assert bootstrap.status_code == 200
        bootstrap_token = str(bootstrap.json()["csrf_token"])
        headers = {
            "Origin": origin or str(settings.frontend_origin).rstrip("/"),
        }
        if not omit_csrf_header:
            headers[settings.csrf_header_name] = csrf_header or bootstrap_token
        response = await client.post(
            "/api/v1/auth/google",
            json=payload if payload is not None else {"credential": CREDENTIAL},
            headers=headers,
        )
        session_token = response.cookies.get(settings.effective_session_cookie_name)
        csrf_token = response.cookies.get(settings.effective_csrf_cookie_name)

    return GoogleHttpResult(
        bootstrap_token=bootstrap_token,
        response=response,
        session_token=session_token,
        csrf_token=csrf_token,
    )


def create_linked_user(
    engine: Engine,
    identity: VerifiedGoogleIdentity,
    *,
    password: bool = False,
    active: bool = True,
    last_login_at: datetime | None = None,
) -> tuple[UUID, UUID]:
    normalized = normalize_email(identity.email)
    with DbSession(engine, expire_on_commit=False) as db:
        user = User(
            email=normalized.canonical,
            normalized_email=normalized.normalized,
            email_verified_at=datetime.now(UTC),
            display_name="Persisted Observer",
            password_hash=hash_password("existing private password")
            if password
            else None,
            is_active=active,
        )
        external = ExternalIdentity(
            user=user,
            provider="google",
            subject=identity.subject,
            email_snapshot=normalized.canonical,
            last_login_at=last_login_at,
        )
        db.add_all((user, external))
        db.commit()
        return user.id, external.id


def create_password_user(engine: Engine, email: str) -> UUID:
    normalized = normalize_email(email)
    with DbSession(engine, expire_on_commit=False) as db:
        user = User(
            email=normalized.canonical,
            normalized_email=normalized.normalized,
            email_verified_at=None,
            display_name="Password Observer",
            password_hash=hash_password("existing private password"),
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user.id


def row_counts(engine: Engine, normalized_email: str) -> tuple[int, int, int]:
    with DbSession(engine) as db:
        user_ids = select(User.id).where(User.normalized_email == normalized_email)
        users = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.normalized_email == normalized_email)
        )
        identities = db.scalar(
            select(func.count())
            .select_from(ExternalIdentity)
            .where(ExternalIdentity.user_id.in_(user_ids))
        )
        sessions = db.scalar(
            select(func.count())
            .select_from(Session)
            .where(Session.user_id.in_(user_ids))
        )
    assert users is not None and identities is not None and sessions is not None
    return users, identities, sessions


def database_totals(engine: Engine) -> tuple[int, int, int]:
    with DbSession(engine) as db:
        users = db.scalar(select(func.count()).select_from(User))
        identities = db.scalar(select(func.count()).select_from(ExternalIdentity))
        sessions = db.scalar(select(func.count()).select_from(Session))
    assert users is not None and identities is not None and sessions is not None
    return users, identities, sessions


def cookie_header(response: httpx.Response, name: str) -> str:
    return next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{name}=")
    )


@pytest.mark.anyio
async def test_existing_identity_login_is_authoritative_safe_and_session_bound(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    identity = verified_identity(email_verified=False, name="Changed Provider Name")
    old_login = datetime.now(UTC) - timedelta(days=2)
    user_id, external_id = create_linked_user(
        google_engine,
        identity,
        password=True,
        last_login_at=old_login,
    )
    with DbSession(google_engine) as db:
        old_session = create_session(db, user_id, settings=google_settings)
        db.commit()
    verifier = FakeGoogleVerifier(identity)
    app = build_google_app(google_engine, google_settings, verifier)

    result = await post_google(
        app,
        google_settings,
        incoming_session=old_session.raw_token,
    )

    assert result.response.status_code == 200, result.response.text
    assert result.response.json() == {
        "id": str(user_id),
        "email": identity.email,
        "email_verified": True,
        "display_name": "Persisted Observer",
        "authentication_methods": ["password", "google"],
    }
    assert result.session_token is not None
    assert result.session_token != old_session.raw_token
    assert result.csrf_token is not None
    validate_csrf_token(
        result.csrf_token,
        settings=google_settings,
        session_token=result.session_token,
    )
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(
            result.bootstrap_token,
            settings=google_settings,
            session_token=result.session_token,
        )

    with DbSession(google_engine) as db:
        user = db.get(User, user_id)
        external = db.get(ExternalIdentity, external_id)
        sessions = list(db.scalars(select(Session).where(Session.user_id == user_id)))
        assert user is not None and external is not None
        assert user.display_name == "Persisted Observer"
        assert user.email == identity.email
        assert external.email_snapshot == identity.email
        assert external.last_login_at is not None
        assert external.last_login_at > old_login
        assert len(sessions) == 2
        assert all(session.revoked_at is None for session in sessions)
        assert any(
            session.token_hash == hash_session_token(result.session_token)
            for session in sessions
        )

    session_cookie = cookie_header(
        result.response, google_settings.effective_session_cookie_name
    )
    csrf_cookie = cookie_header(
        result.response, google_settings.effective_csrf_cookie_name
    )
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "Secure" not in session_cookie
    assert "Domain=" not in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "Secure" not in csrf_cookie
    assert "Domain=" not in csrf_cookie


@pytest.mark.anyio
async def test_new_google_user_is_atomic_normalized_and_contains_no_provider_payload(
    google_engine: Engine,
    google_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    suffix = uuid4().hex
    identity = verified_identity(
        subject=f"{TEST_SUBJECT_PREFIX}{suffix}",
        email=f" Step14-Google-{suffix}+tag@EXAMPLE.COM ",
        name="  Θαλάσσια Ερευνήτρια  ",
    )
    verifier = FakeGoogleVerifier(identity)
    app = build_google_app(google_engine, google_settings, verifier)

    result = await post_google(app, google_settings)

    canonical = f"Step14-Google-{suffix}+tag@example.com"
    normalized = f"{TEST_EMAIL_PREFIX}{suffix}+tag@example.com"
    assert result.response.status_code == 201, result.response.text
    assert result.response.json() == {
        "id": result.response.json()["id"],
        "email": canonical,
        "email_verified": True,
        "display_name": "Θαλάσσια Ερευνήτρια",
        "authentication_methods": ["google"],
    }
    assert result.session_token is not None
    assert result.csrf_token is not None
    assert CREDENTIAL not in result.response.text
    assert CREDENTIAL not in caplog.text

    with DbSession(google_engine) as db:
        user = db.scalar(select(User).where(User.normalized_email == normalized))
        assert user is not None
        external = db.scalar(
            select(ExternalIdentity).where(ExternalIdentity.user_id == user.id)
        )
        session = db.scalar(select(Session).where(Session.user_id == user.id))
        assert external is not None and session is not None
        assert user.email == canonical
        assert user.password_hash is None
        assert user.email_verified_at is not None
        assert user.is_active
        assert external.provider == "google"
        assert external.subject == identity.subject
        assert external.email_snapshot == canonical
        assert external.last_login_at is not None
        assert session.token_hash == hash_session_token(result.session_token)
        assert len(session.token_hash) == 32
        assert not any(
            CREDENTIAL in str(value)
            for value in vars(user).values()
            if isinstance(value, str)
        )
        assert not any(
            CREDENTIAL in str(value)
            for value in vars(external).values()
            if isinstance(value, str)
        )
        assert not hasattr(external, "picture")
        assert not hasattr(external, "credential")


@pytest.mark.anyio
@pytest.mark.parametrize("name", [None, "   ", "x" * 81])
async def test_invalid_provider_name_uses_deterministic_fallback(
    google_engine: Engine,
    google_settings: Settings,
    name: str | None,
) -> None:
    identity = verified_identity(name=name)
    app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(identity),
    )

    result = await post_google(app, google_settings)

    assert result.response.status_code == 201
    assert result.response.json()["display_name"] == "Marine Observer"


@pytest.mark.anyio
async def test_unverified_new_subject_is_generic_and_never_uses_occupied_email(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    user_id = create_password_user(google_engine, email)
    identity = verified_identity(email=email, email_verified=False)
    app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(identity),
    )

    result = await post_google(app, google_settings)

    assert result.response.status_code == 401
    assert result.response.json() == INVALID_CREDENTIALS_DETAIL
    assert row_counts(google_engine, normalize_email(email).normalized) == (1, 0, 0)
    with DbSession(google_engine) as db:
        assert db.get(User, user_id) is not None


@pytest.mark.anyio
async def test_invalid_verified_provider_email_is_a_generic_authentication_failure(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    identity = verified_identity(email="not-a-valid-provider-email")
    app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(identity),
    )
    before = database_totals(google_engine)

    result = await post_google(app, google_settings)

    assert result.response.status_code == 401
    assert result.response.json() == INVALID_CREDENTIALS_DETAIL
    assert database_totals(google_engine) == before


@pytest.mark.anyio
async def test_matching_email_requires_explicit_link_and_changes_nothing(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    user_id = create_password_user(google_engine, email)
    identity = verified_identity(email=email)
    app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(identity),
    )

    result = await post_google(app, google_settings)

    assert result.response.status_code == 409
    assert result.response.json() == LINK_REQUIRED_DETAIL
    assert result.session_token is None
    assert result.csrf_token is None
    assert row_counts(google_engine, normalize_email(email).normalized) == (1, 0, 0)
    with DbSession(google_engine) as db:
        user = db.get(User, user_id)
        assert user is not None
        assert user.password_hash is not None


@pytest.mark.anyio
async def test_inactive_linked_user_is_indistinguishable_and_not_updated(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    identity = verified_identity()
    old_login = datetime.now(UTC) - timedelta(days=2)
    user_id, external_id = create_linked_user(
        google_engine,
        identity,
        active=False,
        last_login_at=old_login,
    )
    app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(identity),
    )

    result = await post_google(app, google_settings)

    assert result.response.status_code == 401
    assert result.response.json() == INVALID_CREDENTIALS_DETAIL
    assert result.session_token is None
    with DbSession(google_engine) as db:
        external = db.get(ExternalIdentity, external_id)
        sessions = list(db.scalars(select(Session).where(Session.user_id == user_id)))
        assert external is not None
        assert external.last_login_at == old_login
        assert sessions == []


@pytest.mark.anyio
async def test_verifier_failure_is_safe_and_does_not_write_or_log_credential(
    google_engine: Engine,
    google_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider_detail = "provider signature diagnostics must remain private"
    verifier = FakeGoogleVerifier(GoogleCredentialVerificationError(provider_detail))
    app = build_google_app(google_engine, google_settings, verifier)

    result = await post_google(app, google_settings)

    assert result.response.status_code == 401
    assert result.response.json() == INVALID_CREDENTIALS_DETAIL
    assert "www-authenticate" not in result.response.headers
    assert CREDENTIAL not in result.response.text
    assert provider_detail not in result.response.text
    assert CREDENTIAL not in caplog.text
    assert provider_detail not in caplog.text
    assert result.session_token is None
    assert CREDENTIAL not in repr(GoogleSignInRequest(credential=SecretStr(CREDENTIAL)))


@pytest.mark.anyio
async def test_missing_google_configuration_fails_safely_without_database_writes(
    google_engine: Engine,
) -> None:
    settings = Settings(google_client_id=None)
    app = build_google_app(google_engine, settings, verifier=None)
    before = database_totals(google_engine)

    result = await post_google(
        app,
        settings,
        payload={"credential": CREDENTIAL},
    )

    assert result.response.status_code == 401
    assert result.response.json() == INVALID_CREDENTIALS_DETAIL
    assert CREDENTIAL not in result.response.text
    assert database_totals(google_engine) == before


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("options", "expected_calls"),
    [
        ({"omit_csrf_header": True}, 0),
        ({"csrf_header": "invalid-csrf-token"}, 0),
        ({"origin": "https://attacker.example"}, 0),
        ({}, 1),
    ],
)
async def test_csrf_and_origin_reject_before_google_verification(
    google_engine: Engine,
    google_settings: Settings,
    options: dict[str, object],
    expected_calls: int,
) -> None:
    verifier = FakeGoogleVerifier(
        GoogleCredentialVerificationError("generic test failure")
    )
    app = build_google_app(google_engine, google_settings, verifier)

    result = await post_google(app, google_settings, **options)  # type: ignore[arg-type]

    if expected_calls == 0:
        assert result.response.status_code == 403
        assert result.response.json() == CSRF_FAILURE_DETAIL
    else:
        assert result.response.status_code == 401
    assert verifier.calls == expected_calls


@pytest.mark.anyio
async def test_malformed_credential_validation_redacts_raw_input(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    candidate = "validation-candidate-must-never-be-echoed"
    verifier = FakeGoogleVerifier(verified_identity())
    app = build_google_app(google_engine, google_settings, verifier)

    result = await post_google(
        app,
        google_settings,
        payload={"credential": [candidate]},
    )

    assert result.response.status_code == 422
    assert candidate not in result.response.text
    assert '"input"' not in result.response.text
    assert verifier.calls == 0


@pytest.mark.anyio
async def test_google_request_rejects_unexpected_fields(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    verifier = FakeGoogleVerifier(verified_identity())
    app = build_google_app(google_engine, google_settings, verifier)

    result = await post_google(
        app,
        google_settings,
        payload={"credential": CREDENTIAL, "access_token": "not-accepted"},
    )

    assert result.response.status_code == 422
    assert verifier.calls == 0


@pytest.mark.anyio
async def test_repeated_google_login_uses_one_identity_and_distinct_sessions(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    identity = verified_identity()
    verifier = FakeGoogleVerifier(identity)
    app = build_google_app(google_engine, google_settings, verifier)

    first = await post_google(app, google_settings)
    second = await post_google(app, google_settings)

    assert first.response.status_code == 201
    assert second.response.status_code == 200
    assert first.session_token is not None and second.session_token is not None
    assert first.session_token != second.session_token
    assert first.response.json()["id"] == second.response.json()["id"]
    assert row_counts(
        google_engine,
        normalize_email(identity.email).normalized,
    ) == (1, 1, 2)


@pytest.mark.anyio
async def test_new_user_session_failure_rolls_back_everything_and_sets_no_cookie(
    google_engine: Engine,
    google_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = verified_identity()

    def fail_session(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise RuntimeError("controlled session failure")

    monkeypatch.setattr(auth_service, "create_session", fail_session)
    app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(identity),
    )

    result = await post_google(
        app,
        google_settings,
        raise_app_exceptions=False,
    )

    assert result.response.status_code == 500
    assert result.response.headers.get_list("set-cookie") == []
    assert row_counts(
        google_engine,
        normalize_email(identity.email).normalized,
    ) == (0, 0, 0)


@pytest.mark.anyio
async def test_existing_identity_session_failure_rolls_back_last_login(
    google_engine: Engine,
    google_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = verified_identity()
    old_login = datetime.now(UTC) - timedelta(days=2)
    user_id, external_id = create_linked_user(
        google_engine,
        identity,
        last_login_at=old_login,
    )

    def fail_session(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise RuntimeError("controlled session failure")

    monkeypatch.setattr(auth_service, "create_session", fail_session)
    app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(identity),
    )

    result = await post_google(
        app,
        google_settings,
        raise_app_exceptions=False,
    )

    assert result.response.status_code == 500
    assert result.response.headers.get_list("set-cookie") == []
    with DbSession(google_engine) as db:
        external = db.get(ExternalIdentity, external_id)
        assert external is not None
        assert external.last_login_at == old_login
        assert (
            db.scalar(
                select(func.count())
                .select_from(Session)
                .where(Session.user_id == user_id)
            )
            == 0
        )


@pytest.mark.anyio
async def test_google_sign_in_never_mutates_password_throttle_state(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    identity = verified_identity()
    with DbSession(google_engine) as db:
        before = list(
            db.execute(
                select(
                    AuthThrottleBucket.id,
                    AuthThrottleBucket.failure_count,
                    AuthThrottleBucket.blocked_until,
                ).order_by(AuthThrottleBucket.id)
            )
        )

    success_app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(identity),
    )
    failure_app = build_google_app(
        google_engine,
        google_settings,
        FakeGoogleVerifier(GoogleCredentialVerificationError("safe")),
    )
    assert (await post_google(success_app, google_settings)).response.status_code == 201
    assert (await post_google(failure_app, google_settings)).response.status_code == 401

    with DbSession(google_engine) as db:
        after = list(
            db.execute(
                select(
                    AuthThrottleBucket.id,
                    AuthThrottleBucket.failure_count,
                    AuthThrottleBucket.blocked_until,
                ).order_by(AuthThrottleBucket.id)
            )
        )
    assert after == before


def test_concurrent_same_subject_recovers_to_one_user_and_identity(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    identity = verified_identity()
    barrier = Barrier(2)

    def sign_in() -> auth_service.GoogleSignInResult:
        verifier = FakeGoogleVerifier(identity, barrier=barrier)
        with DbSession(google_engine, expire_on_commit=False) as db:
            return google_sign_in(
                db,
                GoogleSignInRequest(credential=SecretStr(CREDENTIAL)),
                verifier,
                settings=google_settings,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: sign_in(), range(2)))

    assert sorted(result.created for result in results) == [False, True]
    assert results[0].user.id == results[1].user.id
    assert len({result.raw_session_token for result in results}) == 2
    assert row_counts(
        google_engine,
        normalize_email(identity.email).normalized,
    ) == (1, 1, 2)


def test_concurrent_different_subjects_same_email_never_silently_link(
    google_engine: Engine,
    google_settings: Settings,
) -> None:
    email = f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"
    identities = (
        verified_identity(email=email),
        verified_identity(email=email),
    )
    barrier = Barrier(2)

    def sign_in(identity: VerifiedGoogleIdentity) -> str:
        verifier = FakeGoogleVerifier(identity, barrier=barrier)
        with DbSession(google_engine, expire_on_commit=False) as db:
            try:
                result = google_sign_in(
                    db,
                    GoogleSignInRequest(credential=SecretStr(CREDENTIAL)),
                    verifier,
                    settings=google_settings,
                )
            except GoogleAccountLinkRequiredError:
                return "link_required"
            return "created" if result.created else "existing"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(sign_in, identities))

    assert sorted(outcomes) == ["created", "link_required"]
    assert row_counts(google_engine, normalize_email(email).normalized) == (1, 1, 1)
    with DbSession(google_engine) as db:
        stored_subjects = set(
            db.scalars(
                select(ExternalIdentity.subject).where(
                    ExternalIdentity.subject.in_(
                        [identity.subject for identity in identities]
                    )
                )
            )
        )
    assert len(stored_subjects) == 1
