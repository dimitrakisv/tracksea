from sqlalchemy.orm import configure_mappers

from app.db.metadata import Base


def test_authentication_models_are_registered_with_metadata() -> None:
    configure_mappers()

    assert {
        "auth_throttle_buckets",
        "external_identities",
        "sessions",
        "users",
    }.issubset(Base.metadata.tables)
