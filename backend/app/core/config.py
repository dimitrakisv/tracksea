from functools import lru_cache
from typing import Self

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_CSRF_SECRET = "development-only-change-this-csrf-secret"
DEVELOPMENT_AUTH_THROTTLE_SECRET = "development-only-change-this-auth-throttle-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "TrackSea API"
    environment: str = Field(default="local")
    database_url: str = Field(
        default="postgresql+psycopg://tracksea:tracksea_dev_password@localhost:5432/tracksea"
    )
    session_lifetime_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0)
    session_last_seen_interval_seconds: int = Field(default=5 * 60, gt=0)
    session_cookie_name: str | None = Field(default=None, min_length=1)
    session_cookie_secure: bool = False
    frontend_origin: AnyHttpUrl = AnyHttpUrl("http://localhost:5173")
    csrf_secret: SecretStr = Field(
        default=SecretStr(DEVELOPMENT_CSRF_SECRET),
        min_length=32,
    )
    csrf_cookie_name: str | None = Field(default=None, min_length=1)
    csrf_header_name: str = Field(default="X-CSRF-Token", min_length=1)
    csrf_token_ttl_seconds: int = Field(default=60 * 60, gt=0)
    auth_throttle_secret: SecretStr = Field(
        default=SecretStr(DEVELOPMENT_AUTH_THROTTLE_SECRET),
        min_length=32,
    )
    auth_account_failure_limit: int = Field(default=5, gt=0)
    auth_ip_failure_limit: int = Field(default=20, gt=0)
    auth_throttle_window_seconds: int = Field(default=15 * 60, gt=0)
    auth_block_seconds: int = Field(default=15 * 60, gt=0)
    google_client_id: str | None = None

    @field_validator("google_client_id", mode="before")
    @classmethod
    def normalize_optional_google_client_id(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @property
    def effective_session_cookie_name(self) -> str:
        if self.session_cookie_name is not None:
            return self.session_cookie_name
        if self.session_cookie_secure:
            return "__Host-tracksea_session"
        return "tracksea_session"

    @property
    def effective_csrf_cookie_name(self) -> str:
        if self.csrf_cookie_name is not None:
            return self.csrf_cookie_name
        if self.session_cookie_secure:
            return "__Host-tracksea_csrf"
        return "tracksea_csrf"

    @model_validator(mode="after")
    def validate_session_cookie_security(self) -> Self:
        if self.environment != "local" and not self.session_cookie_secure:
            raise ValueError(
                "Secure session cookies are required outside local development."
            )
        if (
            self.effective_session_cookie_name.startswith("__Host-")
            and not self.session_cookie_secure
        ):
            raise ValueError("__Host- session cookies require Secure=true.")
        if (
            self.effective_csrf_cookie_name.startswith("__Host-")
            and not self.session_cookie_secure
        ):
            raise ValueError("__Host- CSRF cookies require Secure=true.")
        if len(self.csrf_secret.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("CSRF secret must contain at least 32 bytes.")
        if (
            self.environment != "local"
            and self.csrf_secret.get_secret_value() == DEVELOPMENT_CSRF_SECRET
        ):
            raise ValueError(
                "The development CSRF secret cannot be used outside local."
            )
        if len(self.auth_throttle_secret.get_secret_value().encode("utf-8")) < 32:
            raise ValueError(
                "Authentication throttle secret must contain at least 32 bytes."
            )
        if (
            self.environment != "local"
            and self.auth_throttle_secret.get_secret_value()
            == DEVELOPMENT_AUTH_THROTTLE_SECRET
        ):
            raise ValueError(
                "The development authentication throttle secret cannot be used "
                "outside local."
            )
        if (
            self.frontend_origin.path not in {"", "/"}
            or self.frontend_origin.query is not None
            or self.frontend_origin.fragment is not None
            or self.frontend_origin.username is not None
            or self.frontend_origin.password is not None
        ):
            raise ValueError(
                "Frontend origin must contain only scheme, host, and port."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
