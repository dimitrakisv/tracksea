from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from google.auth import exceptions as google_exceptions
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token


@dataclass(frozen=True, slots=True)
class VerifiedGoogleIdentity:
    """Minimal provider evidence; callers enforce verified email for write flows."""

    subject: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


class GoogleCredentialVerificationError(Exception):
    """A safe generic failure that never includes provider credential data."""


class GoogleCredentialVerifier(Protocol):
    """Injectable boundary used by future Google authentication services."""

    def verify(self, credential: str) -> VerifiedGoogleIdentity:
        """Cryptographically verify and map one Google ID credential."""


GoogleTokenVerifier = Callable[[str, GoogleRequest, str], Mapping[str, object]]


class GoogleIdTokenVerifier:
    """Verify Google ID tokens with Google's maintained implementation."""

    def __init__(
        self,
        client_id: str | None,
        *,
        verify_token: GoogleTokenVerifier | None = None,
    ) -> None:
        self._client_id = client_id.strip() or None if client_id is not None else None
        self._verify_token = verify_token or _verify_google_id_token

    def verify(self, credential: str) -> VerifiedGoogleIdentity:
        if self._client_id is None:
            raise GoogleCredentialVerificationError(
                "Google credential could not be verified."
            )

        try:
            claims = self._verify_token(
                credential,
                GoogleRequest(),
                self._client_id,
            )
        except (google_exceptions.GoogleAuthError, ValueError, TypeError):
            raise GoogleCredentialVerificationError(
                "Google credential could not be verified."
            ) from None

        return _map_verified_identity(claims)


def _verify_google_id_token(
    credential: str,
    request: GoogleRequest,
    audience: str,
) -> Mapping[str, object]:
    claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
        credential,
        request,
        audience=audience,
    )
    return cast(Mapping[str, object], claims)


def _map_verified_identity(claims: Mapping[str, object]) -> VerifiedGoogleIdentity:
    try:
        subject = _required_string(claims, "sub")
        email = _required_string(claims, "email")
        email_verified = claims["email_verified"]
        if not isinstance(email_verified, bool):
            raise ValueError
        name = _optional_string(claims, "name")
        picture = _optional_string(claims, "picture")
    except (KeyError, TypeError, ValueError):
        raise GoogleCredentialVerificationError(
            "Google credential could not be verified."
        ) from None

    return VerifiedGoogleIdentity(
        subject=subject,
        email=email,
        email_verified=email_verified,
        name=name,
        picture=picture,
    )


def _required_string(claims: Mapping[str, object], name: str) -> str:
    value = claims[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError
    return value.strip()


def _optional_string(claims: Mapping[str, object], name: str) -> str | None:
    value = claims.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError
    return value.strip() or None
