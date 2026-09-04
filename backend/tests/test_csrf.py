import base64
import hmac
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import Depends, FastAPI
from pydantic import ValidationError

from app.auth.csrf import (
    CsrfValidationError,
    issue_csrf_token,
    validate_csrf_request,
    validate_csrf_token,
    validate_trusted_origin,
)
from app.auth.dependencies import require_csrf
from app.auth.sessions import hash_session_token
from app.core.config import DEVELOPMENT_CSRF_SECRET, Settings, get_settings
from app.main import create_app

TEST_SECRET = "test-csrf-secret-with-at-least-32-bytes"
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
TOKEN_PATTERN = re.compile(r"^v1\.\d+\.\d+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "csrf_secret": TEST_SECRET,
        "frontend_origin": "http://localhost:5173",
        "session_cookie_secure": False,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def alter_segment(token: str, index: int) -> str:
    segments = token.split(".")
    value = segments[index]
    replacement = "A" if value[0] != "A" else "B"
    segments[index] = replacement + value[1:]
    return ".".join(segments)


def settings_dependency(settings: Settings) -> Callable[[], Awaitable[Settings]]:
    async def dependency() -> Settings:
        return settings

    return dependency


def protected_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_settings] = settings_dependency(settings)

    @app.api_route(
        "/protected",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        dependencies=[Depends(require_csrf)],
    )
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    return app


async def request_with_csrf(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    method: str = "POST",
    cookie_token: str | None = None,
    header_token: str | None = None,
    origin: str | None = "http://localhost:5173",
    referer: str | None = None,
    session_token: str | None = None,
) -> httpx.Response:
    client.cookies.clear()
    if cookie_token is not None:
        client.cookies.set(settings.effective_csrf_cookie_name, cookie_token)
    if session_token is not None:
        client.cookies.set(settings.effective_session_cookie_name, session_token)
    headers: dict[str, str] = {}
    if header_token is not None:
        headers[settings.csrf_header_name] = header_token
    if origin is not None:
        headers["Origin"] = origin
    if referer is not None:
        headers["Referer"] = referer
    return await client.request(method, "/protected", headers=headers)


def test_issued_token_is_random_url_safe_and_has_expected_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    nonces = [bytes(range(32)), bytes(reversed(range(32)))]

    def next_nonce(size: int) -> bytes:
        assert size == 32
        return nonces.pop(0)

    monkeypatch.setattr(secrets, "token_bytes", next_nonce)

    first = issue_csrf_token(settings=settings, now=NOW)
    second = issue_csrf_token(settings=settings, now=NOW)

    assert first != second
    assert TOKEN_PATTERN.fullmatch(first)
    assert TOKEN_PATTERN.fullmatch(second)
    version, issued_at, expires_at, nonce, _ = first.split(".")
    assert version == "v1"
    assert int(expires_at) - int(issued_at) == settings.csrf_token_ttl_seconds
    assert len(base64.urlsafe_b64decode(nonce + "==")) == 32


def test_valid_token_is_accepted() -> None:
    settings = make_settings()
    token = issue_csrf_token(settings=settings, now=NOW)

    validate_csrf_token(token, settings=settings, now=NOW + timedelta(seconds=1))


@pytest.mark.parametrize("segment", [1, 2, 3, 4])
def test_modified_token_is_rejected(segment: int) -> None:
    settings = make_settings()
    token = issue_csrf_token(settings=settings, now=NOW)

    with pytest.raises(CsrfValidationError):
        validate_csrf_token(alter_segment(token, segment), settings=settings, now=NOW)


@pytest.mark.parametrize(
    "token",
    ["", "v1", "v1.1.2.nonce.signature.extra", "v2.1.2.nonce.signature"],
)
def test_malformed_token_is_rejected(token: str) -> None:
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(token, settings=make_settings(), now=NOW)


def test_token_signed_with_different_secret_is_rejected() -> None:
    token = issue_csrf_token(settings=make_settings(), now=NOW)
    other_settings = make_settings(
        csrf_secret="another-test-secret-with-at-least-32-bytes"
    )

    with pytest.raises(CsrfValidationError):
        validate_csrf_token(token, settings=other_settings, now=NOW)


def test_expired_and_not_yet_valid_tokens_are_rejected() -> None:
    settings = make_settings(csrf_token_ttl_seconds=60)
    token = issue_csrf_token(settings=settings, now=NOW)

    validate_csrf_token(token, settings=settings, now=NOW + timedelta(seconds=59))
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(token, settings=settings, now=NOW + timedelta(seconds=60))
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(token, settings=settings, now=NOW - timedelta(seconds=1))


def test_session_bound_token_requires_the_same_session() -> None:
    settings = make_settings()
    token = issue_csrf_token(
        settings=settings,
        session_token="session-one",
        now=NOW,
    )

    validate_csrf_token(
        token,
        settings=settings,
        session_token="session-one",
        now=NOW,
    )
    for session_token in (None, "session-two"):
        with pytest.raises(CsrfValidationError):
            validate_csrf_token(
                token,
                settings=settings,
                session_token=session_token,
                now=NOW,
            )


def test_anonymous_token_cannot_be_reused_with_a_session() -> None:
    settings = make_settings()
    token = issue_csrf_token(settings=settings, now=NOW)

    with pytest.raises(CsrfValidationError):
        validate_csrf_token(
            token,
            settings=settings,
            session_token="session-one",
            now=NOW,
        )


def test_token_does_not_expose_secret_or_session_material() -> None:
    settings = make_settings()
    session_token = "a-raw-session-token-that-must-not-leak"
    token = issue_csrf_token(
        settings=settings,
        session_token=session_token,
        now=NOW,
    )
    digest = hash_session_token(session_token)

    assert TEST_SECRET not in token
    assert session_token not in token
    assert digest.hex() not in token
    assert base64.urlsafe_b64encode(digest).decode().rstrip("=") not in token


def test_double_submit_comparisons_use_constant_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    token = issue_csrf_token(settings=settings, now=NOW)
    original_compare_digest = hmac.compare_digest
    comparisons: list[tuple[bytes, bytes]] = []

    def recording_compare_digest(left: bytes, right: bytes) -> bool:
        comparisons.append((left, right))
        return original_compare_digest(left, right)

    monkeypatch.setattr(hmac, "compare_digest", recording_compare_digest)

    validate_csrf_request(
        cookie_token=token,
        header_token=token,
        origin="http://localhost:5173",
        referer=None,
        session_token=None,
        settings=settings,
        now=NOW,
    )

    assert (token.encode(), token.encode()) in comparisons
    assert len(comparisons) == 2


@pytest.mark.parametrize(
    "origin",
    [
        "https://localhost:5173",
        "http://localhost:5174",
        "http://evil.example",
        "http://localhost:5173.evil.example",
        "http://evil.example/http://localhost:5173",
    ],
)
def test_incorrect_or_lookalike_origins_are_rejected(origin: str) -> None:
    with pytest.raises(CsrfValidationError):
        validate_trusted_origin(
            origin=origin,
            referer=None,
            trusted_origin="http://localhost:5173",
        )


def test_origin_comparison_normalizes_default_ports() -> None:
    validate_trusted_origin(
        origin="http://example.com:80",
        referer=None,
        trusted_origin="http://example.com",
    )


def test_referer_is_used_only_when_origin_is_missing() -> None:
    validate_trusted_origin(
        origin=None,
        referer="http://localhost:5173/observations?draft=1",
        trusted_origin="http://localhost:5173",
    )

    with pytest.raises(CsrfValidationError):
        validate_trusted_origin(
            origin="http://evil.example",
            referer="http://localhost:5173/valid",
            trusted_origin="http://localhost:5173",
        )


@pytest.mark.parametrize(
    ("origin", "referer"),
    [
        (None, None),
        (None, "http://evil.example/path"),
        (None, "not-a-url"),
    ],
)
def test_missing_or_invalid_origin_evidence_is_rejected(
    origin: str | None,
    referer: str | None,
) -> None:
    with pytest.raises(CsrfValidationError):
        validate_trusted_origin(
            origin=origin,
            referer=referer,
            trusted_origin="http://localhost:5173",
        )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.anyio
async def test_dependency_accepts_valid_unsafe_requests(method: str) -> None:
    settings = make_settings()
    token = issue_csrf_token(settings=settings)
    transport = httpx.ASGITransport(app=protected_app(settings))

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await request_with_csrf(
            client,
            settings,
            method=method,
            cookie_token=token,
            header_token=token,
        )

    assert response.status_code == 200


@pytest.mark.anyio
async def test_dependency_skips_safe_requests() -> None:
    transport = httpx.ASGITransport(app=protected_app(make_settings()))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/protected")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "failure",
    [
        "missing_cookie",
        "missing_header",
        "mismatch",
        "tampered",
        "wrong_origin",
        "missing_origin",
        "session_binding",
    ],
)
@pytest.mark.anyio
async def test_dependency_returns_one_generic_error_for_all_failures(
    failure: str,
) -> None:
    settings = make_settings()
    token = issue_csrf_token(settings=settings)
    cookie_token: str | None = token
    header_token: str | None = token
    origin: str | None = "http://localhost:5173"
    session_token: str | None = None
    if failure == "missing_cookie":
        cookie_token = None
    elif failure == "missing_header":
        header_token = None
    elif failure == "mismatch":
        header_token = issue_csrf_token(settings=settings)
    elif failure == "tampered":
        cookie_token = header_token = alter_segment(token, 4)
    elif failure == "wrong_origin":
        origin = "http://localhost:5173.evil.example"
    elif failure == "missing_origin":
        origin = None
    else:
        session_token = "different-session-context"
    transport = httpx.ASGITransport(app=protected_app(settings))

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await request_with_csrf(
            client,
            settings,
            cookie_token=cookie_token,
            header_token=header_token,
            origin=origin,
            session_token=session_token,
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "code": "csrf_failed",
            "message": "Request could not be verified.",
        }
    }
    assert token not in response.text


@pytest.mark.anyio
async def test_bootstrap_endpoint_returns_token_and_readable_local_cookie() -> None:
    settings = make_settings()
    app = create_app()
    app.dependency_overrides[get_settings] = settings_dependency(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/auth/csrf")

    assert response.status_code == 200
    assert set(response.json()) == {"csrf_token"}
    token = response.json()["csrf_token"]
    assert TOKEN_PATTERN.fullmatch(token)
    assert response.cookies[settings.effective_csrf_cookie_name] == token
    assert TEST_SECRET not in response.text
    assert response.headers["cache-control"] == "no-store"
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" not in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Secure" not in set_cookie
    assert "Domain=" not in set_cookie


@pytest.mark.anyio
async def test_bootstrap_endpoint_uses_host_cookie_in_secure_environments() -> None:
    settings = make_settings(
        environment="production",
        frontend_origin="https://tracksea.example",
        session_cookie_secure=True,
        csrf_secret="production-csrf-secret-with-at-least-32-bytes",
    )
    app = create_app()
    app.dependency_overrides[get_settings] = settings_dependency(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://tracksea.example",
    ) as client:
        response = await client.get("/api/v1/auth/csrf")

    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith("__Host-tracksea_csrf=")
    assert "Secure" in set_cookie
    assert "HttpOnly" not in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Domain=" not in set_cookie


@pytest.mark.anyio
async def test_bootstrap_token_is_bound_when_session_cookie_is_present() -> None:
    settings = make_settings()
    app = create_app()
    app.dependency_overrides[get_settings] = settings_dependency(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        client.cookies.set(settings.effective_session_cookie_name, "session-one")
        response = await client.get("/api/v1/auth/csrf")

    token = response.json()["csrf_token"]
    validate_csrf_token(token, settings=settings, session_token="session-one")
    with pytest.raises(CsrfValidationError):
        validate_csrf_token(token, settings=settings, session_token="session-two")
    assert "session-one" not in response.text


@pytest.mark.anyio
async def test_health_endpoint_remains_available() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200


def test_csrf_secret_is_masked_and_validated() -> None:
    settings = make_settings()

    assert TEST_SECRET not in repr(settings)
    with pytest.raises(ValidationError, match="at least 32"):
        make_settings(csrf_secret="too-short")
    with pytest.raises(ValidationError, match="development CSRF secret"):
        make_settings(
            environment="production",
            frontend_origin="https://tracksea.example",
            session_cookie_secure=True,
            csrf_secret=DEVELOPMENT_CSRF_SECRET,
        )
