from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.db.session import create_db_engine


def test_create_db_engine_uses_configured_database_url() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://tracksea:tracksea_dev_password@postgres:5432/tracksea"
    )

    engine = create_db_engine(settings)

    assert isinstance(engine, Engine)
    assert make_url(str(engine.url)).host == "postgres"
