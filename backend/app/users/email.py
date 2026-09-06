from dataclasses import dataclass

from pydantic import EmailStr, TypeAdapter, ValidationError

_EMAIL_ADAPTER = TypeAdapter(EmailStr)


class InvalidEmailError(ValueError):
    """Raised when an email address cannot be safely canonicalized."""


@dataclass(frozen=True, slots=True)
class NormalizedEmail:
    """Canonical address and its case-insensitive database comparison value."""

    canonical: str
    normalized: str


def normalize_email(value: str) -> NormalizedEmail:
    """Build canonical and comparison forms without provider alias rewriting.

    Pydantic removes surrounding whitespace, preserves local-part casing, and
    canonicalizes Unicode/IDNA domains. Only the comparison form is case-folded.
    """

    try:
        canonical = str(_EMAIL_ADAPTER.validate_python(value))
    except ValidationError:
        raise InvalidEmailError("Enter a valid email address.") from None

    return NormalizedEmail(
        canonical=canonical,
        normalized=canonical.casefold(),
    )
