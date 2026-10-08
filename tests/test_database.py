from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

import healthcheck
from src.database import check_database_health
from src.document_registry import DocumentRegistry
from src.domain import ConfigurationError

TEST_DATABASE_URL = URL.create("postgresql+psycopg", database="registry")


def test_registry_startup_probes_connection_and_schema() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value

    with (
        patch(
            "src.document_repository.create_database_engine", return_value=engine
        ),
    ):
        DocumentRegistry(TEST_DATABASE_URL)

    assert connection.execute.call_count == 2
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements[0] == "SELECT 1"
    assert "FROM documents" in statements[1]


def test_registry_startup_sanitizes_connection_failure() -> None:
    error = OperationalError("connect", {}, Exception("password=topsecret"))

    with (
        patch("src.document_repository.create_database_engine", side_effect=error),
        pytest.raises(ConfigurationError, match="schema is incompatible") as caught,
    ):
        DocumentRegistry(TEST_DATABASE_URL)

    assert "topsecret" not in str(caught.value)


def test_registry_startup_rejects_incompatible_schema() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.side_effect = [
        MagicMock(),
        OperationalError("schema", {}, Exception("missing column")),
    ]

    with (
        patch(
            "src.document_repository.create_database_engine", return_value=engine
        ),
        pytest.raises(ConfigurationError, match="schema is incompatible"),
    ):
        DocumentRegistry(TEST_DATABASE_URL)

    engine.dispose.assert_called_once()


def test_database_health_probes_and_disposes_engine() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value

    with patch("src.database.create_database_engine", return_value=engine):
        check_database_health(TEST_DATABASE_URL)

    connection.execute.assert_called_once()
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"
    engine.dispose.assert_called_once()


def test_database_health_sanitizes_connection_failure() -> None:
    error = OperationalError("connect", {}, Exception("password=topsecret"))

    with (
        patch("src.database.create_database_engine", side_effect=error),
        pytest.raises(ConfigurationError, match="database is unavailable") as caught,
    ):
        check_database_health(TEST_DATABASE_URL)

    assert "topsecret" not in str(caught.value)


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
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        healthcheck, "database_url_from_env", lambda: TEST_DATABASE_URL
    )
    probe = MagicMock()
    monkeypatch.setattr(healthcheck, "check_database_health", probe)

    assert healthcheck.main() == 0
    probe.assert_called_once_with(TEST_DATABASE_URL)
    assert capsys.readouterr().out == "Database healthy\n"
