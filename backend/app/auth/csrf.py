import base64
import binascii
import hmac
import secrets
from datetime import UTC, datetime
from hashlib import sha256
from ipaddress import ip_address
from urllib.parse import SplitResult, urlsplit

from starlette.responses import Response

from app.auth.sessions import hash_session_token
from app.core.config import Settings, get_settings

CSRF_TOKEN_VERSION = "v1"
CSRF_NONCE_BYTES = 32


class CsrfValidationError(Exception):
    """A generic CSRF failure that does not reveal validation details."""


def issue_csrf_token(
    *,
    settings: Settings | None = None,
    session_token: str | None = None,
    now: datetime | None = None,
) -> str:
    """Issue a versioned token bound to anonymous or current-session context."""

    selected_settings = settings or get_settings()
    issued_at = int(_as_utc(now).timestamp())
    expires_at = issued_at + selected_settings.csrf_token_ttl_seconds
    nonce = _encode_urlsafe(secrets.token_bytes(CSRF_NONCE_BYTES))
    payload = f"{CSRF_TOKEN_VERSION}.{issued_at}.{expires_at}.{nonce}"
    signature = _sign(payload, session_token=session_token, settings=selected_settings)
    return f"{payload}.{_encode_urlsafe(signature)}"


def validate_csrf_token(
    token: str,
    *,
    settings: Settings | None = None,
    session_token: str | None = None,
    now: datetime | None = None,
) -> None:
    """Validate token format, signature, lifetime, and optional session binding."""

    selected_settings = settings or get_settings()
    try:
        version, issued_text, expires_text, nonce_text, signature_text = token.split(
            "."
        )
        if version != CSRF_TOKEN_VERSION:
            raise ValueError
        issued_at = int(issued_text)
        expires_at = int(expires_text)
        nonce = _decode_urlsafe(nonce_text)
        signature = _decode_urlsafe(signature_text)
        if len(nonce) != CSRF_NONCE_BYTES or len(signature) != sha256().digest_size:
            raise ValueError
        if expires_at - issued_at != selected_settings.csrf_token_ttl_seconds:
            raise ValueError

        payload = f"{version}.{issued_at}.{expires_at}.{nonce_text}"
        expected_signature = _sign(
            payload,
            session_token=session_token,
            settings=selected_settings,
        )
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError

        current_time = _as_utc(now).timestamp()
        if issued_at > current_time or expires_at <= current_time:
            raise ValueError
    except (ValueError, UnicodeError, binascii.Error):
        raise CsrfValidationError("Request could not be verified.") from None


def validate_csrf_request(
    *,
    cookie_token: str | None,
    header_token: str | None,
    origin: str | None,
    referer: str | None,
    session_token: str | None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> None:
    """Validate signed double-submit values and the browser's trusted origin."""

    selected_settings = settings or get_settings()
    if cookie_token is None or header_token is None:
        raise CsrfValidationError("Request could not be verified.")
    if not hmac.compare_digest(
        cookie_token.encode("utf-8"),
        header_token.encode("utf-8"),
    ):
        raise CsrfValidationError("Request could not be verified.")

    validate_csrf_token(
        cookie_token,
        settings=selected_settings,
        session_token=session_token,
        now=now,
    )
    validate_trusted_origin(
        origin=origin,
        referer=referer,
        trusted_origin=str(selected_settings.frontend_origin),
    )


def validate_trusted_origin(
    *,
    origin: str | None,
    referer: str | None,
    trusted_origin: str,
) -> None:
    """Require an exact scheme, host, and effective-port match."""

    try:
        expected = _parse_origin(trusted_origin, allow_resource_url=False)
        if origin is not None:
            candidate = _parse_origin(origin, allow_resource_url=False)
        elif referer is not None:
            candidate = _parse_origin(referer, allow_resource_url=True)
        else:
            raise ValueError
        if candidate != expected:
            raise ValueError
    except (ValueError, UnicodeError):
        raise CsrfValidationError("Request could not be verified.") from None


def set_csrf_cookie(
    response: Response,
    token: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Set the readable double-submit cookie using the shared security mode."""

    selected_settings = settings or get_settings()
    response.set_cookie(
        key=selected_settings.effective_csrf_cookie_name,
        value=token,
        max_age=selected_settings.csrf_token_ttl_seconds,
        path="/",
        secure=selected_settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )


def _sign(payload: str, *, session_token: str | None, settings: Settings) -> bytes:
    binding = (
        b"anonymous"
        if session_token is None
        else b"session:" + hash_session_token(session_token)
    )
    message = payload.encode("ascii") + b"." + binding
    secret = settings.csrf_secret.get_secret_value().encode("utf-8")
    return hmac.digest(secret, message, "sha256")


def _parse_origin(value: str, *, allow_resource_url: bool) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (not allow_resource_url and (parsed.path not in {"", "/"} or parsed.query))
    ):
        raise ValueError

    host = _normalize_host(parsed)
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise ValueError from None
    return parsed.scheme, host, port


def _normalize_host(parsed: SplitResult) -> str:
    host = parsed.hostname
    if host is None:
        raise ValueError
    try:
        return ip_address(host).compressed
    except ValueError:
        return host.encode("idna").decode("ascii").casefold()


def _encode_urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_urlsafe(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(
        (value + padding).encode("ascii"),
        altchars=b"-_",
        validate=True,
    )


def _as_utc(value: datetime | None) -> datetime:
    selected = value or datetime.now(UTC)
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError("CSRF timestamps must be timezone-aware.")
    return selected.astimezone(UTC)
