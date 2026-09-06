from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import close_all_sessions

from alembic import command
from alembic.config import Config
from app.core.config import Settings, get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
LOCAL_POSTGRESQL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "postgres"})
TEST_DATABASE_PATTERN = re.compile(r"^tracksea_test_[0-9a-f]{32}$")


@dataclass(slots=True)
class TestDatabaseState:
    source_url: URL
    test_url: URL
    database_name: str
    previous_database_url: str | None
    cleaned_up: bool = False


TEST_DATABASE_STATE = pytest.StashKey[TestDatabaseState]()


def pytest_configure(config: pytest.Config) -> None:
    source_url = make_url(Settings().database_url)
    _validate_source_url(source_url)
    database_name = f"tracksea_test_{uuid4().hex}"
    assert TEST_DATABASE_PATTERN.fullmatch(database_name)
    test_url = source_url.set(database=database_name)
    state = TestDatabaseState(
        source_url=source_url,
        test_url=test_url,
        database_name=database_name,
        previous_database_url=os.environ.get("DATABASE_URL"),
    )

    try:
        _create_database(state)
        os.environ["DATABASE_URL"] = _url_string(test_url)
        get_settings.cache_clear()
        command.upgrade(_alembic_config(), "head")
    except Exception:
        _cleanup_database(state)
        raise

    config.stash[TEST_DATABASE_STATE] = state


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    state = session.config.stash.get(TEST_DATABASE_STATE, None)
    if state is not None:
        _cleanup_database(state)


def pytest_unconfigure(config: pytest.Config) -> None:
    state = config.stash.get(TEST_DATABASE_STATE, None)
    if state is not None:
        _cleanup_database(state)


@pytest.fixture(scope="session", autouse=True)
def isolated_postgresql_database(pytestconfig: pytest.Config) -> str:
    state = pytestconfig.stash[TEST_DATABASE_STATE]
    resolved = make_url(Settings().database_url)
    assert resolved.database == state.database_name
    assert resolved.database != state.source_url.database
    assert TEST_DATABASE_PATTERN.fullmatch(state.database_name)
    return _url_string(state.test_url)


@pytest.fixture(scope="session")
def source_database_name(pytestconfig: pytest.Config) -> str | None:
    return pytestconfig.stash[TEST_DATABASE_STATE].source_url.database


def _validate_source_url(url: URL) -> None:
    if not url.drivername.startswith("postgresql"):
        raise pytest.UsageError("Backend tests require PostgreSQL.")
    if url.host not in LOCAL_POSTGRESQL_HOSTS:
        raise pytest.UsageError(
            "Backend tests may create an isolated database only on local PostgreSQL."
        )
    if url.database in {None, "", "postgres", "template0", "template1"}:
        raise pytest.UsageError(
            "Backend tests require a configured local application database."
        )


def _alembic_config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _maintenance_url(url: URL) -> str:
    return _url_string(url.set(drivername="postgresql", database="postgres"))


def _url_string(url: URL) -> str:
    return url.render_as_string(hide_password=False)


def _create_database(state: TestDatabaseState) -> None:
    with psycopg.connect(_maintenance_url(state.source_url), autocommit=True) as db:
        db.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(state.database_name))
        )


def _cleanup_database(state: TestDatabaseState) -> None:
    if state.cleaned_up:
        return

    close_all_sessions()
    session_module = sys.modules.get("app.db.session")
    if isinstance(session_module, ModuleType):
        engine = getattr(session_module, "engine", None)
        if engine is not None:
            engine.dispose()

    try:
        with psycopg.connect(_maintenance_url(state.source_url), autocommit=True) as db:
            db.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (state.database_name,),
            )
            db.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(state.database_name)
                )
            )
    finally:
        if state.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = state.previous_database_url
        get_settings.cache_clear()
        state.cleaned_up = True
