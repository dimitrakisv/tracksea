from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "TrackSea API"
    environment: str = Field(default="local")
    database_url: str = Field(
        default="postgresql+psycopg://tracksea:tracksea@localhost:5432/tracksea"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
