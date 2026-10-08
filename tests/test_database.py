import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

import healthcheck
from src.database import check_database_health
from src.document_registry import DocumentRegistry
from src.domain import ConfigurationError


def test_registry_startup_initializes_schema_and_health_query(tmp_path: Path) -> None:
    database_url = URL.create(
        "sqlite+pysqlite", database=str(tmp_path / "registry.sqlite3")
    )

    DocumentRegistry(database_url)
    check_database_health(database_url)

    engine = create_engine(database_url)
    try:
        assert inspect(engine).has_table("documents")
    finally:
        engine.dispose()


def test_registry_startup_sanitizes_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_engine(_database_url: URL) -> None:
        raise OperationalError("connect", {}, Exception("password=topsecret"))

    monkeypatch.setattr("src.document_repository.create_database_engine", fail_engine)
    database_url = URL.create("postgresql+psycopg", database="registry")

    with pytest.raises(ConfigurationError, match="cannot be initialized") as error:
        DocumentRegistry(database_url)

    assert "topsecret" not in str(error.value)


def test_registry_startup_rejects_incompatible_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "registry.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE documents (document_id TEXT PRIMARY KEY)")
    database_url = URL.create("sqlite+pysqlite", database=str(database_path))

    with pytest.raises(ConfigurationError, match="cannot be initialized"):
        DocumentRegistry(database_url)


def test_database_health_sanitizes_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_engine(_database_url: URL) -> None:
        raise OperationalError("connect", {}, Exception("password=topsecret"))

    monkeypatch.setattr("src.database.create_database_engine", fail_engine)
    database_url = URL.create("postgresql+psycopg", database="registry")

    with pytest.raises(ConfigurationError, match="database is unavailable") as error:
        check_database_health(database_url)

    assert "topsecret" not in str(error.value)


def test_healthcheck_command_reports_failure_without_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database_url = URL.create("postgresql+psycopg", password="topsecret")
    monkeypatch.setattr(healthcheck, "database_url_from_env", lambda: database_url)

    def fail_health(_database_url: URL) -> None:
        raise ConfigurationError("Document registry database is unavailable")

    monkeypatch.setattr(healthcheck, "check_database_health", fail_health)

    assert healthcheck.main() == 1
    output = capsys.readouterr()
    assert "unavailable" in output.err
    assert "topsecret" not in output.err


def test_healthcheck_command_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = URL.create(
        "sqlite+pysqlite", database=str(tmp_path / "registry.sqlite3")
    )
    monkeypatch.setattr(healthcheck, "database_url_from_env", lambda: database_url)

    assert healthcheck.main() == 0
    assert capsys.readouterr().out == "Database healthy\n"
