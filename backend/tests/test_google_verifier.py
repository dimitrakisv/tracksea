from collections.abc import Callable, Mapping
from typing import cast

import pytest
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from pydantic import ValidationError

from app.auth.google import (
    GoogleCredentialVerificationError,
    GoogleCredentialVerifier,
    GoogleIdTokenVerifier,
    VerifiedGoogleIdentity,
)
from app.core.config import Settings
from app.main import create_app

CLIENT_ID = "tracksea-test.apps.googleusercontent.com"
CREDENTIAL = "candidate-google-id-credential-must-remain-private"
VALID_CLAIMS: dict[str, object] = {
    "sub": "google-subject-123",
    "email": "observer@example.com",
    "email_verified": True,
    "name": "Marine Observer",
    "picture": "https://example.com/profile.jpg",
    "iss": "https://accounts.google.com",
    "aud": CLIENT_ID,
    "exp": 2_000_000_000,
}


def install_provider_result(
    result: Mapping[str, object] | Exception,
) -> tuple[
    list[tuple[str, GoogleRequest, str]],
    Callable[[str, GoogleRequest, str], Mapping[str, object]],
]:
    calls: list[tuple[str, GoogleRequest, str]] = []

    def verify(
        credential: str,
        request: GoogleRequest,
        audience: str,
    ) -> Mapping[str, object]:
        calls.append((credential, request, audience))
        if isinstance(result, Exception):
            raise result
        return result

    return calls, verify


def test_google_configuration_is_optional_trimmed_and_startup_safe() -> None:
    assert Settings().google_client_id is None
    assert Settings(google_client_id="   ").google_client_id is None
    assert Settings(google_client_id=f"  {CLIENT_ID}  ").google_client_id == CLIENT_ID
    assert create_app().title == "TrackSea API"

    with pytest.raises(ValidationError):
        Settings.model_validate({"google_client_id": 42})


@pytest.mark.parametrize("client_id", [None, "", "   "])
def test_missing_configuration_fails_before_provider_or_network_call(
    client_id: str | None,
) -> None:
    provider_called = False

    def reject_provider_call(
        credential: str,
        request: GoogleRequest,
        audience: str,
    ) -> Mapping[str, object]:
        del credential, request, audience
        nonlocal provider_called
        provider_called = True
        raise AssertionError(
            "Provider verification must not run without configuration."
        )

    with pytest.raises(GoogleCredentialVerificationError) as error:
        GoogleIdTokenVerifier(client_id, verify_token=reject_provider_call).verify(
            CREDENTIAL
        )

    assert not provider_called
    assert CREDENTIAL not in str(error.value)
    assert CREDENTIAL not in repr(error.value)


def test_verified_claims_map_to_minimal_immutable_identity() -> None:
    calls, provider = install_provider_result(VALID_CLAIMS)

    identity = GoogleIdTokenVerifier(CLIENT_ID, verify_token=provider).verify(
        CREDENTIAL
    )

    assert identity == VerifiedGoogleIdentity(
        subject="google-subject-123",
        email="observer@example.com",
        email_verified=True,
        name="Marine Observer",
        picture="https://example.com/profile.jpg",
    )
    assert calls[0][0] == CREDENTIAL
    assert calls[0][2] == CLIENT_ID
    assert set(identity.__dataclass_fields__) == {
        "subject",
        "email",
        "email_verified",
        "name",
        "picture",
    }
    assert not hasattr(identity, "exp")
    assert not hasattr(identity, "aud")
    assert not hasattr(identity, "credential")


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("sub", None),
        ("sub", ""),
        ("sub", "   "),
        ("sub", 123),
        ("email", None),
        ("email", ""),
        ("email", 123),
        ("email_verified", None),
        ("email_verified", "true"),
        ("email_verified", 1),
        ("name", 123),
        ("picture", 123),
    ],
)
def test_missing_empty_or_invalid_claim_types_fail_safely(
    claim: str,
    value: object,
) -> None:
    claims = dict(VALID_CLAIMS)
    if value is None:
        claims.pop(claim)
    else:
        claims[claim] = value
    _, provider = install_provider_result(claims)

    with pytest.raises(GoogleCredentialVerificationError) as error:
        GoogleIdTokenVerifier(CLIENT_ID, verify_token=provider).verify(CREDENTIAL)

    assert str(error.value) == "Google credential could not be verified."
    assert CREDENTIAL not in repr(error.value)
    assert repr(claims) not in repr(error.value)


def test_unverified_email_remains_false_and_optional_hints_may_be_absent() -> None:
    claims = dict(VALID_CLAIMS)
    claims["email_verified"] = False
    claims.pop("name")
    claims.pop("picture")
    _, provider = install_provider_result(claims)

    identity = GoogleIdTokenVerifier(CLIENT_ID, verify_token=provider).verify(
        CREDENTIAL
    )

    assert identity.email_verified is False
    assert identity.name is None
    assert identity.picture is None


@pytest.mark.parametrize(
    "provider_error",
    [
        ValueError("wrong audience"),
        ValueError("expired token"),
        ValueError("invalid signature"),
        ValueError("malformed token"),
        GoogleAuthError("wrong issuer"),  # type: ignore[no-untyped-call]
    ],
)
def test_provider_failures_map_to_one_safe_error_without_logging(
    provider_error: Exception,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, provider = install_provider_result(provider_error)

    with pytest.raises(GoogleCredentialVerificationError) as error:
        GoogleIdTokenVerifier(CLIENT_ID, verify_token=provider).verify(CREDENTIAL)

    assert str(error.value) == "Google credential could not be verified."
    assert CREDENTIAL not in repr(error.value)
    assert CREDENTIAL not in caplog.text
    assert str(provider_error) not in str(error.value)


def test_protocol_accepts_a_fake_for_future_service_tests() -> None:
    class FakeVerifier:
        def verify(self, credential: str) -> VerifiedGoogleIdentity:
            del credential
            return VerifiedGoogleIdentity(
                subject="fake-subject",
                email="fake@example.com",
                email_verified=True,
                name=None,
                picture=None,
            )

    verifier = cast(GoogleCredentialVerifier, FakeVerifier())

    assert verifier.verify("test-only-credential").subject == "fake-subject"
