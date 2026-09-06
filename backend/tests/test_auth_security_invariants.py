from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as DbSession

from app.auth.csrf import issue_csrf_token
from app.auth.dependencies import get_google_credential_verifier
from app.auth.google import VerifiedGoogleIdentity
from app.auth.models import AuthThrottleBucket, Session
from app.auth.passwords import hash_password
from app.auth.sessions import create_session
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.users.email import normalize_email
from app.users.models import ExternalIdentity, User

VALID_PASSWORD = "a private ocean passphrase"
CSRF_FAILURE = {
    "detail": {
        "code": "csrf_failed",
        "message": "Request could not be verified.",
    }
}


@dataclass(frozen=True, slots=True)
class UnsafeEndpoint:
    name: str
    method: str
    path: str
    authenticated: bool
    expected_status: int


UNSAFE_ENDPOINTS = (
    UnsafeEndpoint("register", "POST", "/api/v1/auth/register", False, 201),
    UnsafeEndpoint("login", "POST", "/api/v1/auth/login", False, 200),
    UnsafeEndpoint("logout", "POST", "/api/v1/auth/logout", True, 204),
    UnsafeEndpoint("google", "POST", "/api/v1/auth/google", False, 201),
    UnsafeEndpoint("google_link", "POST", "/api/v1/auth/google/link", True, 200),
    UnsafeEndpoint("profile", "PATCH", "/api/v1/users/me", True, 200),
)
CSRF_CASES = (
    "missing_both",
    "mismatched",
    "invalid_origin",
    "valid",
)


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    user_id: UUID | None
    email: str
    raw_session_token: str | None


@dataclass(frozen=True, slots=True)
class AuthDomainState:
    user_ids: tuple[UUID, ...]
    identity_ids: tuple[UUID, ...]
    sessions: tuple[tuple[UUID, datetime | None], ...]
    throttle_buckets: tuple[tuple[UUID, int, datetime | None], ...]


class FakeGoogleVerifier:
    def __init__(self, identity: VerifiedGoogleIdentity) -> None:
        self.identity = identity

    def verify(self, credential: str) -> VerifiedGoogleIdentity:
        assert credential
        return self.identity


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def password_hash() -> str:
    return hash_password(VALID_PASSWORD)


@pytest.fixture
def security_settings() -> Settings:
    return Settings(google_client_id="tracksea-test.apps.googleusercontent.com")


@pytest.fixture
def security_engine(security_settings: Settings) -> Generator[Engine, None, None]:
    engine = create_engine(security_settings.database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


def build_app(
    engine: Engine,
    settings: Settings,
    verifier: FakeGoogleVerifier,
) -> FastAPI:
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


def create_request_identity(
    engine: Engine,
    settings: Settings,
    password_digest: str,
    *,
    session_required: bool,
) -> RequestIdentity:
    suffix = uuid4().hex
    email = f"step21-security-{suffix}@example.com"
    normalized = normalize_email(email)
    with DbSession(engine, expire_on_commit=False) as db:
        user = User(
            email=normalized.canonical,
            normalized_email=normalized.normalized,
            display_name="Security Observer",
            password_hash=password_digest,
            is_active=True,
        )
        db.add(user)
        db.flush()
        raw_session_token = None
        if session_required:
            raw_session_token = create_session(db, user.id, settings=settings).raw_token
        db.commit()
        return RequestIdentity(user.id, user.email, raw_session_token)


def request_payload(endpoint: UnsafeEndpoint, identity: RequestIdentity) -> object:
    if endpoint.name == "register":
        return {
            "email": f"step21-register-{uuid4().hex}@example.com",
            "password": VALID_PASSWORD,
            "display_name": "Security Registration",
        }
    if endpoint.name == "login":
        return {"email": identity.email, "password": VALID_PASSWORD}
    if endpoint.name in {"google", "google_link"}:
        return {"credential": "transient-test-credential"}
    if endpoint.name == "profile":
        return {"display_name": "Updated Security Observer"}
    return None


def csrf_material(
    settings: Settings,
    raw_session_token: str | None,
    case: str,
) -> tuple[str | None, str | None, str]:
    token = issue_csrf_token(
        settings=settings,
        session_token=raw_session_token,
    )
    cookie: str | None = token
    header: str | None = token
    origin = str(settings.frontend_origin).rstrip("/")

    if case == "missing_both":
        cookie = None
        header = None
    elif case == "mismatched":
        header = issue_csrf_token(
            settings=settings,
            session_token=raw_session_token,
        )
    elif case == "invalid_origin":
        origin = "https://hostile.example"
    return cookie, header, origin


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", UNSAFE_ENDPOINTS, ids=lambda item: item.name)
@pytest.mark.parametrize("csrf_case", CSRF_CASES)
async def test_every_unsafe_endpoint_enforces_csrf_and_trusted_origin(
    endpoint: UnsafeEndpoint,
    csrf_case: str,
    security_engine: Engine,
    security_settings: Settings,
    password_hash: str,
) -> None:
    needs_user = endpoint.name != "register" and endpoint.name != "google"
    identity = (
        create_request_identity(
            security_engine,
            security_settings,
            password_hash,
            session_required=endpoint.authenticated,
        )
        if needs_user
        else RequestIdentity(
            None,
            f"step21-google-{uuid4().hex}@example.com",
            None,
        )
    )
    verifier = FakeGoogleVerifier(
        VerifiedGoogleIdentity(
            subject=f"step21-subject-{uuid4().hex}",
            email=identity.email,
            email_verified=True,
            name="Security Observer",
            picture=None,
        )
    )
    app = build_app(security_engine, security_settings, verifier)
    cookie, header, origin = csrf_material(
        security_settings,
        identity.raw_session_token,
        csrf_case,
    )
    headers = {"Origin": origin}
    if header is not None:
        headers[security_settings.csrf_header_name] = header

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        if identity.raw_session_token is not None:
            client.cookies.set(
                security_settings.effective_session_cookie_name,
                identity.raw_session_token,
            )
        if cookie is not None:
            client.cookies.set(
                security_settings.effective_csrf_cookie_name,
                cookie,
            )
        response = await client.request(
            endpoint.method,
            endpoint.path,
            json=request_payload(endpoint, identity),
            headers=headers,
        )

    if csrf_case == "valid":
        assert response.status_code == endpoint.expected_status
    else:
        assert response.status_code == 403
        assert response.json() == CSRF_FAILURE


def auth_domain_state(engine: Engine) -> AuthDomainState:
    with DbSession(engine) as db:
        return AuthDomainState(
            user_ids=tuple(db.scalars(select(User.id).order_by(User.id))),
            identity_ids=tuple(
                db.scalars(select(ExternalIdentity.id).order_by(ExternalIdentity.id))
            ),
            sessions=tuple(
                db.execute(
                    select(Session.id, Session.revoked_at).order_by(Session.id)
                ).tuples()
            ),
            throttle_buckets=tuple(
                db.execute(
                    select(
                        AuthThrottleBucket.id,
                        AuthThrottleBucket.failure_count,
                        AuthThrottleBucket.blocked_until,
                    ).order_by(AuthThrottleBucket.id)
                ).tuples()
            ),
        )


@pytest.mark.anyio
async def test_safe_gets_do_not_create_or_revoke_authentication_state(
    security_engine: Engine,
    security_settings: Settings,
    password_hash: str,
) -> None:
    identity = create_request_identity(
        security_engine,
        security_settings,
        password_hash,
        session_required=True,
    )
    assert identity.raw_session_token is not None
    verifier = FakeGoogleVerifier(
        VerifiedGoogleIdentity(
            subject=f"unused-{uuid4().hex}",
            email=identity.email,
            email_verified=True,
            name=None,
            picture=None,
        )
    )
    app = build_app(security_engine, security_settings, verifier)
    before = auth_domain_state(security_engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        csrf = await client.get("/api/v1/auth/csrf")
        client.cookies.set(
            security_settings.effective_session_cookie_name,
            identity.raw_session_token,
        )
        current_user = await client.get("/api/v1/auth/me")

    assert csrf.status_code == 200
    assert current_user.status_code == 200
    assert auth_domain_state(security_engine) == before


@pytest.mark.anyio
async def test_authentication_routes_never_approve_wildcard_credentialed_cors(
    security_engine: Engine,
    security_settings: Settings,
) -> None:
    verifier = FakeGoogleVerifier(
        VerifiedGoogleIdentity(
            subject="unused-subject",
            email="unused@example.com",
            email_verified=True,
            name=None,
            picture=None,
        )
    )
    app = build_app(security_engine, security_settings, verifier)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://hostile.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-CSRF-Token",
            },
        )

    assert response.headers.get("Access-Control-Allow-Origin") != "*"
    assert response.headers.get("Access-Control-Allow-Credentials") != "true"
