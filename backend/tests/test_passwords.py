import unicodedata
from uuid import uuid4

import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordPolicyCode,
    PasswordPolicyError,
    hash_password,
    normalize_password,
    validate_password,
    verify_and_update_password,
    verify_dummy_password,
    verify_password,
)
from app.users.schemas import AuthenticationMethod, UserResponse


def test_password_normalization_applies_nfc_only() -> None:
    decomposed = "  " + "e\u0301" * 15 + "  "

    normalized = normalize_password(decomposed)

    assert normalized == "  " + "\u00e9" * 15 + "  "
    assert normalized.startswith("  ")
    assert normalized.endswith("  ")
    assert unicodedata.is_normalized("NFC", normalized)


@pytest.mark.parametrize(
    ("password", "expected_code"),
    [
        ("x" * 14, PasswordPolicyCode.TOO_SHORT),
        ("x" * 129, PasswordPolicyCode.TOO_LONG),
        ("Mailcreated5240", PasswordPolicyCode.COMMON),
        ("TrackSea-Password", PasswordPolicyCode.COMMON),
    ],
)
def test_password_policy_rejects_invalid_candidates(
    password: str,
    expected_code: PasswordPolicyCode,
) -> None:
    with pytest.raises(PasswordPolicyError) as error:
        validate_password(password)

    assert error.value.code is expected_code
    assert password not in str(error.value)


@pytest.mark.parametrize(
    "password",
    [
        "x" * MIN_PASSWORD_LENGTH,
        "x" * MAX_PASSWORD_LENGTH,
        "\u03ba" * MIN_PASSWORD_LENGTH,
        "a valid password with spaces",
        "lowercaselettersonly",
    ],
)
def test_password_policy_accepts_length_unicode_spaces_and_no_composition_rules(
    password: str,
) -> None:
    assert validate_password(password) == unicodedata.normalize("NFC", password)


def test_hashes_are_salted_and_verify() -> None:
    password = "a unique ocean passphrase"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != password
    assert first_hash != second_hash
    assert first_hash.startswith("$argon2id$")
    assert verify_password(password, first_hash)
    assert verify_password(password, second_hash)
    assert not verify_password("an incorrect ocean passphrase", first_hash)


def test_unicode_equivalent_password_verifies() -> None:
    decomposed = "e\u0301" * MIN_PASSWORD_LENGTH
    composed = "\u00e9" * MIN_PASSWORD_LENGTH

    password_hash = hash_password(decomposed)

    assert verify_password(composed, password_hash)


def test_current_hash_does_not_require_update() -> None:
    password = "a current ocean passphrase"
    password_hash = hash_password(password)

    verified, updated_hash = verify_and_update_password(password, password_hash)

    assert verified
    assert updated_hash is None


def test_stale_hash_is_replaced_after_successful_verification() -> None:
    password = "an older ocean passphrase"
    stale_hasher = PasswordHash((Argon2Hasher(time_cost=2),))
    stale_hash = stale_hasher.hash(password)

    verified, updated_hash = verify_and_update_password(password, stale_hash)

    assert verified
    assert updated_hash is not None
    assert updated_hash != stale_hash
    assert verify_password(password, updated_hash)


def test_unknown_hash_fails_safely() -> None:
    assert not verify_password("a candidate ocean passphrase", "not-a-valid-hash")
    assert verify_and_update_password(
        "a candidate ocean passphrase",
        "not-a-valid-hash",
    ) == (False, None)


def test_dummy_hash_verification_executes_without_authenticating() -> None:
    assert not verify_dummy_password("an unknown account password")


def test_public_user_schema_excludes_password_data() -> None:
    response = UserResponse(
        id=uuid4(),
        email="observer@example.com",
        email_verified=False,
        display_name="Observer",
        authentication_methods=(AuthenticationMethod.PASSWORD,),
    )

    serialized = response.model_dump()
    assert "password" not in serialized
    assert "password_hash" not in serialized
