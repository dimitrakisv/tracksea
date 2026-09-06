from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session as DbSession

from app.auth.models import Session
from app.core.config import Settings
from app.users.email import normalize_email
from app.users.models import ExternalIdentity, User

FRONTEND_ORIGIN = "http://localhost:5173"
LOCAL_POSTGRESQL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "postgres"})
SYSTEM_DATABASES = frozenset({"postgres", "template0", "template1"})
SAFE_USER_KEYS = {
    "id",
    "email",
    "email_verified",
    "display_name",
    "authentication_methods",
}


def test_authentication_flow_through_frontend_proxy() -> None:
    test_id = uuid4().hex
    email = f"step22-fullstack-{test_id}@example.com"
    normalized_email = normalize_email(email).normalized
    password = f"Step22-{secrets.token_urlsafe(24)}"
    settings = Settings()
    database_url = _validated_cleanup_url(settings.database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    registered_user_id: UUID | None = None
    registration_attempted = False

    try:
        with _frontend_client() as client:
            health = client.get("/api/v1/health")
            _assert_frontend_proxy_response(health, 200)

            anonymous_me = client.get("/api/v1/auth/me")
            _assert_frontend_proxy_response(anonymous_me, 401)
            assert anonymous_me.json()["detail"]["code"] == "authentication_required"

            csrf = client.get("/api/v1/auth/csrf")
            _assert_frontend_proxy_response(csrf, 200)
            csrf_token = csrf.json()["csrf_token"]
            assert isinstance(csrf_token, str) and csrf_token
            _assert_local_cookie(
                _cookie_header(csrf, settings.effective_csrf_cookie_name),
                http_only=False,
            )
            assert settings.effective_csrf_cookie_name in client.cookies

            registration_attempted = True
            registration = client.post(
                "/api/v1/auth/register",
                headers={"Origin": FRONTEND_ORIGIN, "X-CSRF-Token": csrf_token},
                json={
                    "email": email,
                    "password": password,
                    "display_name": "Step 22 Full Stack",
                },
            )
            _assert_frontend_proxy_response(registration, 201)
            user = registration.json()
            assert set(user) == SAFE_USER_KEYS
            assert user["email"] == email
            assert user["email_verified"] is False
            assert user["display_name"] == "Step 22 Full Stack"
            assert user["authentication_methods"] == ["password"]
            registered_user_id = UUID(user["id"])

            _assert_local_cookie(
                _cookie_header(registration, settings.effective_session_cookie_name),
                http_only=True,
            )
            _assert_local_cookie(
                _cookie_header(registration, settings.effective_csrf_cookie_name),
                http_only=False,
            )
            assert settings.effective_session_cookie_name in client.cookies

            authenticated_me = client.get("/api/v1/auth/me")
            _assert_frontend_proxy_response(authenticated_me, 200)
            assert authenticated_me.json()["id"] == user["id"]

            authenticated_csrf = client.get("/api/v1/auth/csrf")
            _assert_frontend_proxy_response(authenticated_csrf, 200)
            logout = client.post(
                "/api/v1/auth/logout",
                headers={
                    "Origin": FRONTEND_ORIGIN,
                    "X-CSRF-Token": authenticated_csrf.json()["csrf_token"],
                },
            )
            _assert_frontend_proxy_response(logout, 204)
            cleared_session = _cookie_header(
                logout, settings.effective_session_cookie_name
            )
            assert "max-age=0" in cleared_session.lower()
            assert settings.effective_session_cookie_name not in client.cookies

            logged_out_me = client.get("/api/v1/auth/me")
            _assert_frontend_proxy_response(logged_out_me, 401)
            assert logged_out_me.json()["detail"]["code"] == "authentication_required"
    finally:
        if registration_attempted:
            _cleanup_test_account(
                engine,
                user_id=registered_user_id,
                normalized_email=normalized_email,
            )
        engine.dispose()


@contextmanager
def _frontend_client() -> Iterator[httpx.Client]:
    try:
        with httpx.Client(
            base_url=FRONTEND_ORIGIN,
            timeout=10,
            follow_redirects=False,
        ) as client:
            yield client
    except httpx.TransportError as error:
        pytest.fail(
            "The Step 22 full-stack test requires the local frontend, backend, "
            "and PostgreSQL services to be running and reachable through "
            f"{FRONTEND_ORIGIN}. ({type(error).__name__})"
        )


def _validated_cleanup_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("Step 22 cleanup requires PostgreSQL.")
    if url.host not in LOCAL_POSTGRESQL_HOSTS:
        pytest.fail("Step 22 cleanup is restricted to local PostgreSQL.")
    if url.database in {None, "", *SYSTEM_DATABASES}:
        pytest.fail("Step 22 cleanup refuses PostgreSQL system databases.")
    return url


def _assert_frontend_proxy_response(response: httpx.Response, status: int) -> None:
    assert response.request.url.host == "localhost"
    assert response.request.url.port == 5173
    assert "backend" not in str(response.request.url)
    assert response.status_code == status
    assert response.headers.get("access-control-allow-origin") != "*"


def _cookie_header(response: httpx.Response, name: str) -> str:
    prefix = f"{name}="
    headers = response.headers.get_list("set-cookie")
    matches = [header for header in headers if header.startswith(prefix)]
    assert len(matches) == 1
    return matches[0]


def _assert_local_cookie(header: str, *, http_only: bool) -> None:
    attributes = {part.strip().lower() for part in header.split(";")[1:]}
    assert "path=/" in attributes
    assert "samesite=lax" in attributes
    assert ("httponly" in attributes) is http_only
    assert "secure" not in attributes
    assert all(not attribute.startswith("domain=") for attribute in attributes)


def _cleanup_test_account(
    engine: Engine,
    *,
    user_id: UUID | None,
    normalized_email: str,
) -> None:
    with DbSession(engine) as db:
        statement = select(User).where(User.normalized_email == normalized_email)
        if user_id is not None:
            statement = statement.where(User.id == user_id)
        user = db.scalar(statement)
        if user is not None:
            persisted_id = user.id
            db.delete(user)
            db.commit()
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Session)
                    .where(Session.user_id == persisted_id)
                )
                == 0
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(ExternalIdentity)
                    .where(ExternalIdentity.user_id == persisted_id)
                )
                == 0
            )
        assert (
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.normalized_email == normalized_email)
            )
            == 0
        )
