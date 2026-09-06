from __future__ import annotations

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import NoReturn
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import AnyHttpUrl, SecretStr, ValidationError
from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

import app.auth.service as auth_service
from app.auth.models import AuthThrottleBucket, Session
from app.auth.passwords import hash_password
from app.auth.sessions import create_session
from app.auth.throttling import (
    MISSING_CLIENT_ADDRESS,
    LoginThrottleKeys,
    build_login_throttle_keys,
    canonicalize_client_address,
    cleanup_expired_throttle_buckets,
    derive_throttle_key,
    get_login_retry_after,
    record_login_failure,
)
from app.core.config import DEVELOPMENT_AUTH_THROTTLE_SECRET, Settings, get_settings
from app.db.session import create_db_engine, get_db_session
from app.main import create_app
from app.users.email import normalize_email
from app.users.models import ExternalIdentity, User

TEST_EMAIL_PREFIX = "step11-throttle-"
VALID_PASSWORD = "a private ocean passphrase"
WRONG_PASSWORD = "an incorrect ocean passphrase"
DIRECT_IP = "198.51.100.24"
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
INVALID_CREDENTIALS_RESPONSE = {
    "detail": {
        "code": "invalid_credentials",
        "message": "Email or password is incorrect.",
    }
}
RATE_LIMITED_RESPONSE = {
    "detail": {
        "code": "rate_limited",
        "message": "Too many sign-in attempts. Try again later.",
    }
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def throttle_settings() -> Settings:
    return Settings(
        auth_throttle_secret=SecretStr(f"step11-test-throttle-secret-{uuid4().hex}"),
        auth_account_failure_limit=100,
        auth_ip_failure_limit=100,
        auth_throttle_window_seconds=60,
        auth_block_seconds=60,
    )


@pytest.fixture
def throttle_engine(
    throttle_settings: Settings,
) -> Generator[Engine, None, None]:
    url = make_url(throttle_settings.database_url)
    if url.host not in {"127.0.0.1", "localhost", "postgres"}:
        pytest.fail("Throttle tests require a local PostgreSQL database.")

    engine = create_db_engine(throttle_settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.fail("Local PostgreSQL must be available for throttle tests.")

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


def settings_with_limits(
    base: Settings,
    *,
    account: int = 100,
    ip: int = 100,
    window: int = 60,
    block: int = 60,
) -> Settings:
    return base.model_copy(
        update={
            "auth_account_failure_limit": account,
            "auth_ip_failure_limit": ip,
            "auth_throttle_window_seconds": window,
            "auth_block_seconds": block,
        }
    )


def unique_email() -> str:
    return f"{TEST_EMAIL_PREFIX}{uuid4().hex}@example.com"


def build_test_app(engine: Engine, settings: Settings) -> FastAPI:
    app = create_app()

    def database_override() -> Generator[DbSession, None, None]:
        with DbSession(engine, expire_on_commit=False) as db:
            yield db

    async def settings_override() -> Settings:
        return settings

    app.dependency_overrides[get_db_session] = database_override
    app.dependency_overrides[get_settings] = settings_override
    return app


def create_test_user(
    engine: Engine,
    *,
    email: str,
    password: str | None = VALID_PASSWORD,
    active: bool = True,
    google_identity: bool = False,
) -> UUID:
    normalized = normalize_email(email)
    with DbSession(engine, expire_on_commit=False) as db:
        user = User(
            email=normalized.canonical,
            normalized_email=normalized.normalized,
            display_name="Throttle Observer",
            password_hash=hash_password(password) if password is not None else None,
            is_active=active,
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


async def login_attempt(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    email: str,
    password: str = WRONG_PASSWORD,
    forwarded_for: str | None = None,
) -> httpx.Response:
    bootstrap = await client.get("/api/v1/auth/csrf")
    assert bootstrap.status_code == 200
    csrf_token = bootstrap.json()["csrf_token"]
    headers = {
        settings.csrf_header_name: csrf_token,
        "Origin": str(settings.frontend_origin).rstrip("/"),
    }
    if forwarded_for is not None:
        headers["X-Forwarded-For"] = forwarded_for
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )


def throttle_keys(
    email: str,
    settings: Settings,
    *,
    direct_ip: str = DIRECT_IP,
) -> LoginThrottleKeys:
    return build_login_throttle_keys(
        normalize_email(email).normalized,
        direct_ip,
        settings=settings,
    )


def bucket_for(
    engine: Engine,
    *,
    scope: str,
    key_hash: bytes,
) -> AuthThrottleBucket | None:
    with DbSession(engine) as db:
        bucket = db.scalar(
            select(AuthThrottleBucket).where(
                AuthThrottleBucket.scope == scope,
                AuthThrottleBucket.key_hash == key_hash,
            )
        )
        if bucket is not None:
            db.expunge(bucket)
        return bucket


def count_sessions(engine: Engine, user_id: UUID) -> int:
    with DbSession(engine) as db:
        count = db.scalar(
            select(func.count()).select_from(Session).where(Session.user_id == user_id)
        )
    assert count is not None
    return count


def test_throttle_configuration_defaults_and_secret_validation() -> None:
    settings = Settings()

    assert settings.auth_account_failure_limit == 5
    assert settings.auth_ip_failure_limit == 20
    assert settings.auth_throttle_window_seconds == 900
    assert settings.auth_block_seconds == 900
    assert "**********" in repr(settings.auth_throttle_secret)
    assert settings.auth_throttle_secret.get_secret_value() not in repr(settings)
    assert (
        settings.auth_throttle_secret.get_secret_value()
        != settings.csrf_secret.get_secret_value()
    )

    with pytest.raises(ValidationError):
        Settings(auth_throttle_secret=SecretStr("too-short"))
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            session_cookie_secure=True,
            csrf_secret=SecretStr("production-csrf-secret-with-at-least-32-bytes"),
            auth_throttle_secret=SecretStr(DEVELOPMENT_AUTH_THROTTLE_SECRET),
            frontend_origin=AnyHttpUrl("https://tracksea.example"),
        )


def test_hmac_keys_are_normalized_canonical_scoped_and_secret_specific(
    throttle_settings: Settings,
) -> None:
    first_email = "Observer+Journal@EXAMPLE.COM"
    equivalent_email = "observer+journal@example.com"
    other_email = "observer@example.com"
    first = throttle_keys(first_email, throttle_settings, direct_ip="192.0.2.9")
    equivalent = throttle_keys(
        equivalent_email,
        throttle_settings,
        direct_ip="192.0.2.9",
    )
    other = throttle_keys(other_email, throttle_settings, direct_ip="192.0.2.10")

    assert first.account == equivalent.account
    assert first.account != other.account
    assert first.ip == equivalent.ip
    assert first.ip != other.ip
    assert len(first.account) == 32
    assert len(first.ip) == 32
    assert derive_throttle_key(
        "account",
        "same-source",
        settings=throttle_settings,
    ) != derive_throttle_key("ip", "same-source", settings=throttle_settings)

    other_secret = throttle_settings.model_copy(
        update={
            "auth_throttle_secret": SecretStr(
                "a-different-test-throttle-secret-with-32-bytes"
            )
        }
    )
    assert throttle_keys(first_email, other_secret).account != first.account


def test_client_address_canonicalization_and_safe_fallback() -> None:
    assert canonicalize_client_address("192.0.2.10") == "192.0.2.10"
    assert canonicalize_client_address("2001:0db8:0:0::1") == "2001:db8::1"
    assert canonicalize_client_address(None) == MISSING_CLIENT_ADDRESS
    assert canonicalize_client_address("not-an-ip") == MISSING_CLIENT_ADDRESS


def test_failure_upsert_counts_both_scopes_without_raw_keys(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    email = unique_email()
    keys = throttle_keys(email, throttle_settings)

    with DbSession(throttle_engine) as db:
        record_login_failure(db, keys, settings=throttle_settings, now=NOW)
        record_login_failure(
            db,
            keys,
            settings=throttle_settings,
            now=NOW + timedelta(seconds=1),
        )
        db.commit()

    account = bucket_for(throttle_engine, scope="account", key_hash=keys.account)
    ip = bucket_for(throttle_engine, scope="ip", key_hash=keys.ip)
    assert account is not None
    assert ip is not None
    assert account.failure_count == 2
    assert ip.failure_count == 2
    assert len(account.key_hash) == 32
    assert len(ip.key_hash) == 32
    persisted = repr((account, ip, account.key_hash, ip.key_hash))
    assert normalize_email(email).normalized not in persisted
    assert DIRECT_IP not in persisted


@pytest.mark.anyio
async def test_all_credential_failure_kinds_increment_account_and_ip_buckets(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    wrong_email = unique_email()
    unknown_email = unique_email()
    google_email = unique_email()
    inactive_email = unique_email()
    create_test_user(throttle_engine, email=wrong_email)
    create_test_user(
        throttle_engine,
        email=google_email,
        password=None,
        google_identity=True,
    )
    create_test_user(throttle_engine, email=inactive_email, active=False)
    app = build_test_app(throttle_engine, throttle_settings)
    transport = httpx.ASGITransport(app=app, client=(DIRECT_IP, 41000))

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        responses = [
            await login_attempt(client, throttle_settings, email=wrong_email),
            await login_attempt(client, throttle_settings, email=unknown_email),
            await login_attempt(client, throttle_settings, email=google_email),
            await login_attempt(client, throttle_settings, email=inactive_email),
        ]

    assert all(response.status_code == 401 for response in responses)
    assert all(
        response.json() == INVALID_CREDENTIALS_RESPONSE for response in responses
    )
    for email in (wrong_email, unknown_email, google_email, inactive_email):
        keys = throttle_keys(email, throttle_settings)
        account = bucket_for(
            throttle_engine,
            scope="account",
            key_hash=keys.account,
        )
        assert account is not None
        assert account.failure_count == 1
    ip = bucket_for(
        throttle_engine,
        scope="ip",
        key_hash=throttle_keys(wrong_email, throttle_settings).ip,
    )
    assert ip is not None
    assert ip.failure_count == 4


@pytest.mark.anyio
async def test_account_threshold_blocks_next_request_without_argon(
    throttle_engine: Engine,
    throttle_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_with_limits(throttle_settings, account=2)
    email = unique_email()
    user_id = create_test_user(throttle_engine, email=email)
    app = build_test_app(throttle_engine, settings)
    transport = httpx.ASGITransport(app=app, client=(DIRECT_IP, 41001))

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        first = await login_attempt(client, settings, email=email)
        second = await login_attempt(client, settings, email=email)

        def reject_real_verification(*args: object, **kwargs: object) -> NoReturn:
            raise AssertionError("Blocked login must not run Argon2 verification.")

        def reject_dummy_verification(*args: object, **kwargs: object) -> NoReturn:
            raise AssertionError("Blocked login must not run dummy verification.")

        monkeypatch.setattr(
            auth_service,
            "verify_and_update_password",
            reject_real_verification,
        )
        monkeypatch.setattr(
            auth_service,
            "verify_dummy_password",
            reject_dummy_verification,
        )
        blocked = await login_attempt(
            client,
            settings,
            email=email,
            password=VALID_PASSWORD,
        )

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    assert blocked.json() == RATE_LIMITED_RESPONSE
    assert blocked.headers["Retry-After"].isdigit()
    assert int(blocked.headers["Retry-After"]) > 0
    assert "www-authenticate" not in blocked.headers
    assert email not in blocked.text
    assert "account" not in blocked.text.casefold()
    assert count_sessions(throttle_engine, user_id) == 0


@pytest.mark.anyio
async def test_known_and_unknown_accounts_have_equivalent_public_responses(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    settings = settings_with_limits(throttle_settings, account=2)
    known_email = unique_email()
    unknown_email = unique_email()
    create_test_user(throttle_engine, email=known_email)
    app = build_test_app(throttle_engine, settings)
    transport = httpx.ASGITransport(app=app, client=(DIRECT_IP, 41002))

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        known_failures = [
            await login_attempt(client, settings, email=known_email),
            await login_attempt(client, settings, email=known_email),
        ]
        unknown_failures = [
            await login_attempt(client, settings, email=unknown_email),
            await login_attempt(client, settings, email=unknown_email),
        ]
        known_blocked = await login_attempt(client, settings, email=known_email)
        unknown_blocked = await login_attempt(client, settings, email=unknown_email)

    for response in (*known_failures, *unknown_failures):
        assert response.status_code == 401
        assert response.json() == INVALID_CREDENTIALS_RESPONSE
    for response in (known_blocked, unknown_blocked):
        assert response.status_code == 429
        assert response.json() == RATE_LIMITED_RESPONSE


@pytest.mark.anyio
async def test_ip_threshold_spans_accounts_and_ignores_forwarding_headers(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    settings = settings_with_limits(throttle_settings, ip=2)
    emails = [unique_email() for _ in range(3)]
    app = build_test_app(throttle_engine, settings)
    transport = httpx.ASGITransport(app=app, client=(DIRECT_IP, 41003))

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        first = await login_attempt(
            client,
            settings,
            email=emails[0],
            forwarded_for="203.0.113.1",
        )
        second = await login_attempt(
            client,
            settings,
            email=emails[1],
            forwarded_for="203.0.113.2",
        )
        blocked = await login_attempt(
            client,
            settings,
            email=emails[2],
            forwarded_for="203.0.113.3",
        )

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    direct_keys = throttle_keys(emails[0], settings)
    direct_bucket = bucket_for(
        throttle_engine,
        scope="ip",
        key_hash=direct_keys.ip,
    )
    assert direct_bucket is not None
    assert direct_bucket.failure_count == 2
    for spoofed_ip in ("203.0.113.1", "203.0.113.2", "203.0.113.3"):
        spoofed_keys = throttle_keys(emails[0], settings, direct_ip=spoofed_ip)
        assert (
            bucket_for(
                throttle_engine,
                scope="ip",
                key_hash=spoofed_keys.ip,
            )
            is None
        )


def test_fixed_window_reset_block_expiry_and_retry_after(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    settings = settings_with_limits(
        throttle_settings,
        account=2,
        ip=100,
        window=60,
        block=30,
    )
    keys = throttle_keys(unique_email(), settings)
    with DbSession(throttle_engine) as db:
        record_login_failure(db, keys, settings=settings, now=NOW)
        record_login_failure(
            db,
            keys,
            settings=settings,
            now=NOW + timedelta(seconds=1),
        )
        db.commit()

    with DbSession(throttle_engine) as db:
        assert (
            get_login_retry_after(
                db,
                keys,
                now=NOW + timedelta(seconds=2),
            )
            == 29
        )
        assert (
            get_login_retry_after(
                db,
                keys,
                now=NOW + timedelta(seconds=31),
            )
            is None
        )
        record_login_failure(
            db,
            keys,
            settings=settings,
            now=NOW + timedelta(seconds=31),
        )
        db.commit()

    reset = bucket_for(throttle_engine, scope="account", key_hash=keys.account)
    assert reset is not None
    assert reset.failure_count == 1
    assert reset.window_started_at == NOW + timedelta(seconds=31)
    assert reset.blocked_until is None

    outside_window_keys = throttle_keys(
        unique_email(), settings, direct_ip="192.0.2.55"
    )
    with DbSession(throttle_engine) as db:
        record_login_failure(db, outside_window_keys, settings=settings, now=NOW)
        record_login_failure(
            db,
            outside_window_keys,
            settings=settings,
            now=NOW + timedelta(seconds=61),
        )
        db.commit()
    outside_window = bucket_for(
        throttle_engine,
        scope="account",
        key_hash=outside_window_keys.account,
    )
    assert outside_window is not None
    assert outside_window.failure_count == 1
    assert outside_window.window_started_at == NOW + timedelta(seconds=61)


@pytest.mark.anyio
async def test_success_resets_account_only_and_next_failure_starts_again(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    settings = settings_with_limits(throttle_settings, account=5, ip=20)
    email = unique_email()
    user_id = create_test_user(throttle_engine, email=email)
    keys = throttle_keys(email, settings)
    app = build_test_app(throttle_engine, settings)
    transport = httpx.ASGITransport(app=app, client=(DIRECT_IP, 41004))

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        assert (await login_attempt(client, settings, email=email)).status_code == 401
        assert (await login_attempt(client, settings, email=email)).status_code == 401
        success = await login_attempt(
            client,
            settings,
            email=email,
            password=VALID_PASSWORD,
        )
        subsequent_failure = await login_attempt(client, settings, email=email)

    assert success.status_code == 200
    assert subsequent_failure.status_code == 401
    account = bucket_for(throttle_engine, scope="account", key_hash=keys.account)
    ip = bucket_for(throttle_engine, scope="ip", key_hash=keys.ip)
    assert account is not None
    assert account.failure_count == 1
    assert ip is not None
    assert ip.failure_count == 3
    assert count_sessions(throttle_engine, user_id) == 1


@pytest.mark.anyio
async def test_login_transaction_failure_preserves_account_throttle_reset(
    throttle_engine: Engine,
    throttle_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_with_limits(throttle_settings)
    email = unique_email()
    user_id = create_test_user(throttle_engine, email=email)
    keys = throttle_keys(email, settings)
    with DbSession(throttle_engine) as db:
        record_login_failure(db, keys, settings=settings, now=NOW)
        db.commit()

    def fail_session_creation(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("controlled session creation failure")

    monkeypatch.setattr(auth_service, "create_session", fail_session_creation)
    app = build_test_app(throttle_engine, settings)
    transport = httpx.ASGITransport(
        app=app,
        client=(DIRECT_IP, 41005),
        raise_app_exceptions=False,
    )
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await login_attempt(
            client,
            settings,
            email=email,
            password=VALID_PASSWORD,
        )

    assert response.status_code == 500
    account = bucket_for(throttle_engine, scope="account", key_hash=keys.account)
    assert account is not None
    assert account.failure_count == 1
    assert count_sessions(throttle_engine, user_id) == 0
    assert response.headers.get_list("set-cookie") == []


@pytest.mark.anyio
async def test_throttle_recording_failure_is_not_reported_as_credentials_failure(
    throttle_engine: Engine,
    throttle_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = unique_email()
    user_id = create_test_user(throttle_engine, email=email)

    def fail_recording(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("controlled throttle persistence failure")

    monkeypatch.setattr(auth_service, "record_login_failure", fail_recording)
    app = build_test_app(throttle_engine, throttle_settings)
    transport = httpx.ASGITransport(
        app=app,
        client=(DIRECT_IP, 41006),
        raise_app_exceptions=False,
    )
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await login_attempt(client, throttle_settings, email=email)

    assert response.status_code == 500
    assert count_sessions(throttle_engine, user_id) == 0
    keys = throttle_keys(email, throttle_settings)
    assert bucket_for(throttle_engine, scope="account", key_hash=keys.account) is None
    assert bucket_for(throttle_engine, scope="ip", key_hash=keys.ip) is None


def test_concurrent_failures_do_not_lose_increments_or_duplicate_rows(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    attempts = 8
    keys = throttle_keys(unique_email(), throttle_settings)
    barrier = Barrier(attempts)

    def record_failure(_: int) -> None:
        with DbSession(throttle_engine) as db:
            barrier.wait()
            record_login_failure(
                db,
                keys,
                settings=throttle_settings,
                now=NOW,
            )
            db.commit()

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        list(executor.map(record_failure, range(attempts)))

    with DbSession(throttle_engine) as db:
        rows = list(
            db.scalars(
                select(AuthThrottleBucket).where(
                    or_(
                        and_(
                            AuthThrottleBucket.scope == "account",
                            AuthThrottleBucket.key_hash == keys.account,
                        ),
                        and_(
                            AuthThrottleBucket.scope == "ip",
                            AuthThrottleBucket.key_hash == keys.ip,
                        ),
                    )
                )
            )
        )

    assert len(rows) == 2
    assert {row.scope: row.failure_count for row in rows} == {
        "account": attempts,
        "ip": attempts,
    }


def test_bounded_cleanup_removes_only_stale_throttle_state(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    stale = throttle_keys(unique_email(), throttle_settings, direct_ip="192.0.2.60")
    current = throttle_keys(unique_email(), throttle_settings, direct_ip="192.0.2.61")
    blocked = throttle_keys(unique_email(), throttle_settings, direct_ip="192.0.2.62")
    blocking_settings = settings_with_limits(throttle_settings, account=1, ip=1)
    user_id = create_test_user(throttle_engine, email=unique_email())
    with DbSession(throttle_engine) as db:
        created_session = create_session(
            db, user_id, settings=throttle_settings, now=NOW
        )
        record_login_failure(
            db,
            stale,
            settings=throttle_settings,
            now=NOW - timedelta(seconds=61),
        )
        record_login_failure(db, current, settings=throttle_settings, now=NOW)
        record_login_failure(db, blocked, settings=blocking_settings, now=NOW)
        db.commit()

    with DbSession(throttle_engine) as db:
        first_deleted = cleanup_expired_throttle_buckets(
            db,
            settings=throttle_settings,
            now=NOW,
            limit=1,
        )
        second_deleted = cleanup_expired_throttle_buckets(
            db,
            settings=throttle_settings,
            now=NOW,
            limit=1,
        )
        db.commit()

    assert first_deleted == 1
    assert second_deleted == 1
    assert bucket_for(throttle_engine, scope="account", key_hash=stale.account) is None
    assert bucket_for(throttle_engine, scope="ip", key_hash=stale.ip) is None
    assert bucket_for(throttle_engine, scope="account", key_hash=current.account)
    assert bucket_for(throttle_engine, scope="ip", key_hash=current.ip)
    assert bucket_for(throttle_engine, scope="account", key_hash=blocked.account)
    assert bucket_for(throttle_engine, scope="ip", key_hash=blocked.ip)
    assert count_sessions(throttle_engine, user_id) == 1
    with DbSession(throttle_engine) as db:
        assert db.get(Session, created_session.session_id) is not None


@pytest.mark.anyio
async def test_csrf_and_schema_failures_do_not_increment_throttles(
    throttle_engine: Engine,
    throttle_settings: Settings,
) -> None:
    email = unique_email()
    create_test_user(throttle_engine, email=email)
    keys = throttle_keys(email, throttle_settings)
    app = build_test_app(throttle_engine, throttle_settings)
    transport = httpx.ASGITransport(app=app, client=(DIRECT_IP, 41007))

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        missing_csrf = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": WRONG_PASSWORD},
            headers={"Origin": "http://localhost:5173"},
        )
        bootstrap = await client.get("/api/v1/auth/csrf")
        csrf_token = bootstrap.json()["csrf_token"]
        invalid_origin = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": WRONG_PASSWORD},
            headers={
                throttle_settings.csrf_header_name: csrf_token,
                "Origin": "https://attacker.example",
            },
        )
        malformed = await client.post(
            "/api/v1/auth/login",
            json={"email": email},
            headers={
                throttle_settings.csrf_header_name: csrf_token,
                "Origin": "http://localhost:5173",
            },
        )

    assert missing_csrf.status_code == 403
    assert invalid_origin.status_code == 403
    assert malformed.status_code == 422
    assert bucket_for(throttle_engine, scope="account", key_hash=keys.account) is None
    assert bucket_for(throttle_engine, scope="ip", key_hash=keys.ip) is None
