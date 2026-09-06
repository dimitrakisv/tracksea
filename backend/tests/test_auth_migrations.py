from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from alembic.config import Config
from app.core.config import Settings

HEAD_REVISION = "011d8d16c6cf"
TRACKSEA_TABLES = {
    "alembic_version",
    "auth_throttle_buckets",
    "external_identities",
    "sessions",
    "users",
}
AUTH_TABLES = TRACKSEA_TABLES - {"alembic_version"}
SYSTEM_TABLES = {"spatial_ref_sys"}


def alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    return Config(str(backend_root / "alembic.ini"))


def database_engine() -> Engine:
    return create_engine(Settings().database_url, pool_pre_ping=True)


def public_tables() -> set[str]:
    engine = database_engine()
    try:
        return set(inspect(engine).get_table_names(schema="public"))
    finally:
        engine.dispose()


def current_revision() -> str | None:
    engine = database_engine()
    try:
        with engine.connect() as connection:
            revision = connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            return revision if isinstance(revision, str) else None
    finally:
        engine.dispose()


def reflected_names(items: Iterable[Mapping[str, object]]) -> set[str]:
    names: set[str] = set()
    for item in items:
        name = item.get("name")
        if isinstance(name, str):
            names.add(name)
    return names


def test_suite_uses_a_generated_database_not_the_application_database(
    isolated_postgresql_database: str,
    source_database_name: str | None,
) -> None:
    isolated_name = make_url(isolated_postgresql_database).database

    assert isolated_name is not None
    assert isolated_name.startswith("tracksea_test_")
    assert isolated_name != source_database_name
    assert make_url(Settings().database_url).database == isolated_name


def test_authentication_migration_upgrades_downgrades_and_restores_head() -> None:
    config = alembic_config()

    try:
        command.downgrade(config, "base")
        assert public_tables().isdisjoint(AUTH_TABLES)

        command.upgrade(config, "head")
        assert current_revision() == HEAD_REVISION
        assert public_tables() - SYSTEM_TABLES == TRACKSEA_TABLES

        command.downgrade(config, "base")
        assert public_tables().isdisjoint(AUTH_TABLES)
    finally:
        command.upgrade(config, "head")

    assert current_revision() == HEAD_REVISION
    assert public_tables() - SYSTEM_TABLES == TRACKSEA_TABLES


def test_authentication_migration_has_expected_named_constraints_and_indexes() -> None:
    engine = database_engine()
    try:
        inspector = inspect(engine)
        assert inspector.get_pk_constraint("auth_throttle_buckets")["name"] == (
            "pk_auth_throttle_buckets"
        )
        assert reflected_names(
            inspector.get_unique_constraints("auth_throttle_buckets")
        ) == {"uq_auth_throttle_buckets_scope_key_hash"}
        assert reflected_names(
            inspector.get_check_constraints("auth_throttle_buckets")
        ) == {
            "ck_auth_throttle_buckets_failure_count_nonnegative",
            "ck_auth_throttle_buckets_key_hash_length",
            "ck_auth_throttle_buckets_scope",
        }

        assert inspector.get_pk_constraint("users")["name"] == "pk_users"
        assert reflected_names(inspector.get_unique_constraints("users")) == {
            "uq_users_normalized_email"
        }
        assert reflected_names(inspector.get_check_constraints("users")) == {
            "ck_users_display_name_nonempty",
            "ck_users_email_nonempty",
            "ck_users_normalized_email_nonempty",
        }

        assert inspector.get_pk_constraint("external_identities")["name"] == (
            "pk_external_identities"
        )
        assert reflected_names(
            inspector.get_unique_constraints("external_identities")
        ) == {"uq_external_identities_provider_subject"}
        assert reflected_names(inspector.get_foreign_keys("external_identities")) == {
            "fk_external_identities_user_id_users"
        }
        assert reflected_names(
            inspector.get_check_constraints("external_identities")
        ) == {
            "ck_external_identities_provider",
            "ck_external_identities_subject_nonempty",
        }

        assert inspector.get_pk_constraint("sessions")["name"] == "pk_sessions"
        assert reflected_names(inspector.get_unique_constraints("sessions")) == {
            "uq_sessions_token_hash"
        }
        assert reflected_names(inspector.get_foreign_keys("sessions")) == {
            "fk_sessions_user_id_users"
        }
        assert reflected_names(inspector.get_check_constraints("sessions")) == {
            "ck_sessions_expires_after_creation",
            "ck_sessions_token_hash_length",
        }

        assert {"ix_external_identities_user_id"}.issubset(
            reflected_names(inspector.get_indexes("external_identities"))
        )
        assert {
            "ix_sessions_expires_at",
            "ix_sessions_user_id_revoked_at",
        }.issubset(reflected_names(inspector.get_indexes("sessions")))
    finally:
        engine.dispose()


def test_postgresql_enforces_authentication_uniqueness_and_check_constraints() -> None:
    engine = database_engine()
    first_user_id = uuid4()
    second_user_id = uuid4()
    user_email = f"migration-{uuid4().hex}@example.com"
    provider_subject = f"subject-{uuid4().hex}"
    session_digest = b"s" * 32

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, email, normalized_email, display_name) "
                    "VALUES (:id, :email, :normalized_email, 'Migration User')"
                ),
                {
                    "id": first_user_id,
                    "email": user_email,
                    "normalized_email": user_email,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, email, normalized_email, display_name) "
                    "VALUES (:id, :email, :normalized_email, 'Second User')"
                ),
                {
                    "id": second_user_id,
                    "email": f"second-{user_email}",
                    "normalized_email": f"second-{user_email}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO external_identities "
                    "(id, user_id, provider, subject) "
                    "VALUES (:id, :user_id, 'google', :subject)"
                ),
                {
                    "id": uuid4(),
                    "user_id": first_user_id,
                    "subject": provider_subject,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO sessions "
                    "(id, token_hash, user_id, expires_at) "
                    "VALUES (:id, :token_hash, :user_id, now() + interval '1 hour')"
                ),
                {
                    "id": uuid4(),
                    "token_hash": session_digest,
                    "user_id": first_user_id,
                },
            )

        rejected_statements = [
            (
                "INSERT INTO users "
                "(id, email, normalized_email, display_name) "
                "VALUES (:id, 'duplicate@example.com', :normalized_email, 'Duplicate')",
                {"id": uuid4(), "normalized_email": user_email},
            ),
            (
                "INSERT INTO external_identities "
                "(id, user_id, provider, subject) "
                "VALUES (:id, :user_id, 'google', :subject)",
                {
                    "id": uuid4(),
                    "user_id": second_user_id,
                    "subject": provider_subject,
                },
            ),
            (
                "INSERT INTO sessions "
                "(id, token_hash, user_id, expires_at) "
                "VALUES (:id, :token_hash, :user_id, now() + interval '1 hour')",
                {
                    "id": uuid4(),
                    "token_hash": session_digest,
                    "user_id": second_user_id,
                },
            ),
            (
                "INSERT INTO sessions "
                "(id, token_hash, user_id, expires_at) "
                "VALUES (:id, :token_hash, :user_id, now() + interval '1 hour')",
                {
                    "id": uuid4(),
                    "token_hash": b"short",
                    "user_id": first_user_id,
                },
            ),
            (
                "INSERT INTO auth_throttle_buckets "
                "(id, scope, key_hash) VALUES (:id, 'other', :key_hash)",
                {"id": uuid4(), "key_hash": b"k" * 32},
            ),
            (
                "INSERT INTO auth_throttle_buckets "
                "(id, scope, key_hash) VALUES (:id, 'account', :key_hash)",
                {"id": uuid4(), "key_hash": b"short"},
            ),
            (
                "INSERT INTO auth_throttle_buckets "
                "(id, scope, key_hash, failure_count) "
                "VALUES (:id, 'ip', :key_hash, -1)",
                {"id": uuid4(), "key_hash": b"n" * 32},
            ),
        ]

        for statement, parameters in rejected_statements:
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(text(statement), parameters)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM users WHERE id IN (:first_id, :second_id)"),
                {"first_id": first_user_id, "second_id": second_user_id},
            )
        engine.dispose()
