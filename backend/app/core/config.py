from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def effective_session_cookie_name(self) -> str:
        if self.session_cookie_name is not None:
            return self.session_cookie_name
        if self.session_cookie_secure:
            return "__Host-tracksea_session"
        return "tracksea_session"

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
