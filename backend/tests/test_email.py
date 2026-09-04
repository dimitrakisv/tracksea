import pytest

from app.users.email import InvalidEmailError, normalize_email


def test_valid_email_is_canonicalized_deterministically() -> None:
    first = normalize_email(" User.Name+tag@EXAMPLE.COM ")
    second = normalize_email("User.Name+tag@example.com")

    assert first == second
    assert first.canonical == "User.Name+tag@example.com"
    assert first.normalized == "user.name+tag@example.com"


def test_local_part_aliases_are_not_rewritten() -> None:
    email = normalize_email("First.Last+ocean@GMAIL.COM")

    assert email.canonical == "First.Last+ocean@gmail.com"
    assert email.normalized == "first.last+ocean@gmail.com"


def test_local_part_case_is_preserved_only_in_canonical_value() -> None:
    email = normalize_email("Marine.Observer@Example.com")

    assert email.canonical == "Marine.Observer@example.com"
    assert email.normalized == "marine.observer@example.com"


def test_unicode_and_idna_domains_share_one_canonical_value() -> None:
    unicode_domain = normalize_email("observer@\u30c4.life")
    idna_domain = normalize_email("observer@xn--bdk.life")

    assert unicode_domain == idna_domain
    assert unicode_domain.canonical == "observer@\u30c4.life"


def test_malformed_email_has_safe_error() -> None:
    malformed = "not-an-email"

    with pytest.raises(InvalidEmailError) as error:
        normalize_email(malformed)

    assert str(error.value) == "Enter a valid email address."
    assert malformed not in str(error.value)
