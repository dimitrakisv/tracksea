from __future__ import annotations

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

from app.auth.csrf import validate_csrf_token
from app.auth.dependencies import get_google_credential_verifier
from app.auth.google import (
    GoogleCredentialVerificationError,
    VerifiedGoogleIdentity,
)
from app.auth.models import AuthThrottleBucket, Session
from app.auth.passwords import hash_password
from app.auth.schemas import GoogleSignInRequest
from app.auth.service import GoogleLinkConflictError, link_google_identity
from app.auth.sessions import create_session
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, get_db_session
from app.main import create_app
from app.users.email import normalize_email
from app.users.models import ExternalIdentity, User

EMAIL_PREFIX = "step15-link-"
SUBJECT_PREFIX = "step15-subject-"
CREDENTIAL = "candidate-link-credential-must-remain-private"
INVALID_DETAIL = {
    "detail": {
        "code": "invalid_credentials",
        "message": "Google account could not be verified.",
    }
}
CONFLICT_DETAIL = {
    "detail": {
        "code": "account_conflict",
        "message": "The Google account could not be linked.",
    }
}
CSRF_DETAIL = {
    "detail": {"code": "csrf_failed", "message": "Request could not be verified."}
}


class FakeVerifier:
    def __init__(
        self,
        result: VerifiedGoogleIdentity | Exception,
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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def link_settings() -> Settings:
    return Settings(google_client_id="tracksea-test.apps.googleusercontent.com")


@pytest.fixture
def link_engine(link_settings: Settings) -> Generator[Engine, None, None]:
    url = make_url(link_settings.database_url)
    if url.host not in {"127.0.0.1", "localhost", "postgres"}:
        pytest.fail("Google-link tests require local PostgreSQL.")
    engine = create_db_engine(link_settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.fail("Local PostgreSQL must be available for Google-link tests.")
    yield engine
    with DbSession(engine) as db:
        db.execute(delete(User).where(User.normalized_email.like(f"{EMAIL_PREFIX}%")))
        db.commit()
    engine.dispose()


def identity(
    email: str,
    *,
    subject: str | None = None,
    verified: bool = True,
) -> VerifiedGoogleIdentity:
    return VerifiedGoogleIdentity(
        subject=subject or f"{SUBJECT_PREFIX}{uuid4().hex}",
        email=email,
        email_verified=verified,
        name="Provider Name Not Persisted",
        picture="https://example.com/not-persisted.jpg",
    )


def create_user_session(
    engine: Engine,
    settings: Settings,
    email: str,
    *,
    password: bool = True,
    active: bool = True,
) -> tuple[UUID, UUID, str]:
    normalized = normalize_email(email)
    with DbSession(engine, expire_on_commit=False) as db:
        user = User(
            email=normalized.canonical,
            normalized_email=normalized.normalized,
            email_verified_at=None,
            display_name="Link Observer",
            password_hash=hash_password("private password") if password else None,
            is_active=active,
        )
        db.add(user)
        db.flush()
        created = create_session(db, user.id, settings=settings)
        session = db.get(Session, created.session_id)
        assert session is not None
        session.last_seen_at = datetime.now(UTC)
        db.commit()
        return user.id, created.session_id, created.raw_token


def build_app(engine: Engine, settings: Settings, verifier: FakeVerifier) -> FastAPI:
    app = create_app()

    def database_override() -> Generator[DbSession, None, None]:
        with DbSession(engine, expire_on_commit=False) as db:
            yield db

    async def settings_override() -> Settings:
        return settings

    app.dependency_overrides[get_db_session] = database_override
    app.dependency_overrides[get_settings] = settings_override
    app.dependency_overrides[get_google_credential_verifier] = lambda: verifier
    return app


async def link_request(
    app: FastAPI,
    settings: Settings,
    session_token: str | None,
    *,
    payload: object | None = None,
    origin: str | None = None,
    header: str | None = None,
    omit_header: bool = False,
    omit_cookie: bool = False,
    raise_app_exceptions: bool = True,
) -> tuple[httpx.Response, httpx.Response, str]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        if session_token is not None:
            client.cookies.set(
                settings.effective_session_cookie_name,
                session_token,
                domain="testserver.local",
                path="/",
            )
        bootstrap = await client.get("/api/v1/auth/csrf")
        token = str(bootstrap.json()["csrf_token"])
        if omit_cookie:
            client.cookies.delete(settings.effective_csrf_cookie_name)
        headers = {"Origin": origin or str(settings.frontend_origin).rstrip("/")}
        if not omit_header:
            headers[settings.csrf_header_name] = header or token
        response = await client.post(
            "/api/v1/auth/google/link",
            json=payload or {"credential": CREDENTIAL},
            headers=headers,
        )
        current = await client.get("/api/v1/auth/me")
    return response, current, token


def state(engine: Engine, user_id: UUID) -> tuple[int, int, Session]:
    with DbSession(engine) as db:
        users = db.scalar(select(func.count()).select_from(User))
        identities = db.scalar(
            select(func.count())
            .select_from(ExternalIdentity)
            .where(ExternalIdentity.user_id == user_id)
        )
        sessions = list(db.scalars(select(Session).where(Session.user_id == user_id)))
        assert users is not None and identities is not None and len(sessions) == 1
        db.expunge(sessions[0])
        return users, identities, sessions[0]


@pytest.mark.anyio
async def test_successful_and_idempotent_link_preserve_session_and_csrf(
    link_engine: Engine,
    link_settings: Settings,
) -> None:
    suffix = uuid4().hex
    email = f"{EMAIL_PREFIX}{suffix}@example.com"
    user_id, session_id, raw_session = create_user_session(
        link_engine, link_settings, email
    )
    google = identity(f" {EMAIL_PREFIX.upper()}{suffix.upper()}@EXAMPLE.COM ")
    verifier = FakeVerifier(google)
    app = build_app(link_engine, link_settings, verifier)
    before = state(link_engine, user_id)

    first, current, csrf_token = await link_request(app, link_settings, raw_session)
    second, _, _ = await link_request(app, link_settings, raw_session)

    assert first.status_code == second.status_code == 200
    expected = {
        "id": str(user_id),
        "email": email,
        "email_verified": False,
        "display_name": "Link Observer",
        "authentication_methods": ["password", "google"],
    }
    assert first.json() == second.json() == current.json() == expected
    assert first.headers.get_list("set-cookie") == []
    assert second.headers.get_list("set-cookie") == []
    assert CREDENTIAL not in first.text
    after = state(link_engine, user_id)
    assert after[0] == before[0]
    assert after[1] == 1
    assert after[2].id == session_id == before[2].id
    assert after[2].token_hash == before[2].token_hash
    assert after[2].expires_at == before[2].expires_at
    assert after[2].revoked_at == before[2].revoked_at
    with DbSession(link_engine) as db:
        linked = db.scalar(
            select(ExternalIdentity).where(ExternalIdentity.subject == google.subject)
        )
        assert linked is not None
        assert linked.user_id == user_id
        assert linked.email_snapshot == normalize_email(google.email).canonical
        assert linked.last_login_at is None
        assert not hasattr(linked, "credential")
        assert not hasattr(linked, "picture")
    validate_csrf_token(
        csrf_token,
        settings=link_settings,
        session_token=raw_session,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["unverified", "invalid"])
async def test_provider_failures_are_generic_and_create_no_link(
    link_engine: Engine,
    link_settings: Settings,
    failure: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    email = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    user_id, _, raw_session = create_user_session(link_engine, link_settings, email)
    result: VerifiedGoogleIdentity | Exception
    if failure == "unverified":
        result = identity(email, verified=False)
    else:
        result = GoogleCredentialVerificationError("private provider diagnostic")
    app = build_app(link_engine, link_settings, FakeVerifier(result))

    response, current, _ = await link_request(app, link_settings, raw_session)

    assert response.status_code == 401
    assert response.json() == INVALID_DETAIL
    assert current.status_code == 200
    assert state(link_engine, user_id)[1] == 0
    assert response.headers.get_list("set-cookie") == []
    assert CREDENTIAL not in response.text
    assert CREDENTIAL not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("google_only", [False, True])
async def test_email_mismatch_and_google_only_user_are_generic_conflicts(
    link_engine: Engine,
    link_settings: Settings,
    google_only: bool,
) -> None:
    email = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    user_id, _, raw_session = create_user_session(
        link_engine, link_settings, email, password=not google_only
    )
    provider_email = email if google_only else f"other-{email}"
    app = build_app(link_engine, link_settings, FakeVerifier(identity(provider_email)))

    response, current, _ = await link_request(app, link_settings, raw_session)

    assert response.status_code == 409
    assert response.json() == CONFLICT_DETAIL
    assert current.status_code == 200
    assert state(link_engine, user_id)[1] == 0
    assert response.headers.get_list("set-cookie") == []


@pytest.mark.anyio
async def test_identity_owned_by_another_user_is_not_transferred(
    link_engine: Engine,
    link_settings: Settings,
) -> None:
    email_a = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    email_b = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    user_a, _, session_a = create_user_session(link_engine, link_settings, email_a)
    user_b, _, _ = create_user_session(link_engine, link_settings, email_b)
    google = identity(email_a)
    with DbSession(link_engine) as db:
        db.add(
            ExternalIdentity(
                user_id=user_b,
                provider="google",
                subject=google.subject,
                email_snapshot=email_b,
            )
        )
        db.commit()
    app = build_app(link_engine, link_settings, FakeVerifier(google))

    response, _, _ = await link_request(app, link_settings, session_a)

    assert response.status_code == 409
    assert response.json() == CONFLICT_DETAIL
    assert email_b not in response.text and str(user_b) not in response.text
    with DbSession(link_engine) as db:
        linked = db.scalar(
            select(ExternalIdentity).where(ExternalIdentity.subject == google.subject)
        )
        assert linked is not None and linked.user_id == user_b
    assert state(link_engine, user_a)[1] == 0


@pytest.mark.anyio
async def test_inactive_or_missing_session_rejects_before_verifier(
    link_engine: Engine,
    link_settings: Settings,
) -> None:
    email = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    _, _, inactive_session = create_user_session(
        link_engine, link_settings, email, active=False
    )
    verifier = FakeVerifier(identity(email))
    app = build_app(link_engine, link_settings, verifier)

    inactive, _, _ = await link_request(app, link_settings, inactive_session)
    anonymous, _, _ = await link_request(app, link_settings, None)

    assert inactive.status_code == anonymous.status_code == 401
    assert inactive.json()["detail"]["code"] == "authentication_required"
    assert verifier.calls == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "options",
    [
        {"omit_header": True},
        {"omit_cookie": True},
        {"header": "wrong-token"},
        {"origin": "https://attacker.example"},
    ],
)
async def test_csrf_rejects_before_verifier(
    link_engine: Engine,
    link_settings: Settings,
    options: dict[str, object],
) -> None:
    email = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    _, _, raw_session = create_user_session(link_engine, link_settings, email)
    verifier = FakeVerifier(identity(email))
    app = build_app(link_engine, link_settings, verifier)

    response, _, _ = await link_request(
        app,
        link_settings,
        raw_session,
        **options,  # type: ignore[arg-type]
    )

    assert response.status_code == 403
    assert response.json() == CSRF_DETAIL
    assert verifier.calls == 0


@pytest.mark.anyio
async def test_validation_redacts_credential_and_rejects_extra_fields(
    link_engine: Engine,
    link_settings: Settings,
) -> None:
    email = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    _, _, raw_session = create_user_session(link_engine, link_settings, email)
    verifier = FakeVerifier(identity(email))
    app = build_app(link_engine, link_settings, verifier)

    malformed, _, _ = await link_request(
        app,
        link_settings,
        raw_session,
        payload={"credential": [CREDENTIAL]},
    )
    extra, _, _ = await link_request(
        app,
        link_settings,
        raw_session,
        payload={"credential": CREDENTIAL, "user_id": str(uuid4())},
    )

    assert malformed.status_code == extra.status_code == 422
    assert CREDENTIAL not in malformed.text
    assert verifier.calls == 0


@pytest.mark.anyio
async def test_unexpected_identity_flush_failure_rolls_back_without_cookies(
    link_engine: Engine,
    link_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    user_id, _, raw_session = create_user_session(link_engine, link_settings, email)
    app = build_app(link_engine, link_settings, FakeVerifier(identity(email)))
    original_flush = DbSession.flush

    def fail_identity_flush(db: DbSession, objects: object | None = None) -> None:
        if any(isinstance(record, ExternalIdentity) for record in db.new):
            raise RuntimeError("controlled persistence failure")
        original_flush(db, objects)  # type: ignore[arg-type]

    monkeypatch.setattr(DbSession, "flush", fail_identity_flush)
    response, _, _ = await link_request(
        app,
        link_settings,
        raw_session,
        raise_app_exceptions=False,
    )

    assert response.status_code == 500
    assert response.headers.get_list("set-cookie") == []
    assert state(link_engine, user_id)[1] == 0


@pytest.mark.anyio
async def test_linking_does_not_mutate_password_throttle_buckets(
    link_engine: Engine,
    link_settings: Settings,
) -> None:
    email = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    _, _, raw_session = create_user_session(link_engine, link_settings, email)
    with DbSession(link_engine) as db:
        before = list(
            db.execute(select(AuthThrottleBucket).order_by(AuthThrottleBucket.id))
        )
    app = build_app(link_engine, link_settings, FakeVerifier(identity(email)))

    response, _, _ = await link_request(app, link_settings, raw_session)

    assert response.status_code == 200
    with DbSession(link_engine) as db:
        after = list(
            db.execute(select(AuthThrottleBucket).order_by(AuthThrottleBucket.id))
        )
    assert after == before


def test_concurrent_same_user_same_subject_is_idempotent(
    link_engine: Engine,
    link_settings: Settings,
) -> None:
    email = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    user_id, _, _ = create_user_session(link_engine, link_settings, email)
    google = identity(email)
    barrier = Barrier(2)

    def link() -> str:
        with DbSession(link_engine) as db:
            result = link_google_identity(
                db,
                user_id,
                GoogleSignInRequest(credential=SecretStr(CREDENTIAL)),
                FakeVerifier(google, barrier),
            )
            return str(result.id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: link(), range(2)))

    assert results == [str(user_id), str(user_id)]
    assert state(link_engine, user_id)[1] == 1


def test_concurrent_different_users_same_subject_has_one_owner(
    link_engine: Engine,
    link_settings: Settings,
) -> None:
    email_a = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    email_b = f"{EMAIL_PREFIX}{uuid4().hex}@example.com"
    user_a, _, _ = create_user_session(link_engine, link_settings, email_a)
    user_b, _, _ = create_user_session(link_engine, link_settings, email_b)
    subject = f"{SUBJECT_PREFIX}{uuid4().hex}"
    barrier = Barrier(2)

    def link(user_id: UUID, email: str) -> str:
        with DbSession(link_engine) as db:
            try:
                link_google_identity(
                    db,
                    user_id,
                    GoogleSignInRequest(credential=SecretStr(CREDENTIAL)),
                    FakeVerifier(identity(email, subject=subject), barrier),
                )
            except GoogleLinkConflictError:
                return "conflict"
            return "linked"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda args: link(*args),
                ((user_a, email_a), (user_b, email_b)),
            )
        )

    assert sorted(outcomes) == ["conflict", "linked"]
    with DbSession(link_engine) as db:
        records = list(
            db.scalars(
                select(ExternalIdentity).where(ExternalIdentity.subject == subject)
            )
        )
        assert len(records) == 1
        assert records[0].user_id in {user_a, user_b}
