import pytest
from alembic import command
from alembic.config import Config


def test_initial_migration_renders_registry_schema(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://localhost/simple_rag"
    )
    config = Config("alembic.ini")

    command.upgrade(config, "head", sql=True)

    sql = capsys.readouterr().out
    assert "CREATE TABLE documents" in sql
    assert "source_path VARCHAR NOT NULL" in sql
    assert "UNIQUE (source_path)" in sql
    assert "created_at TIMESTAMP WITH TIME ZONE NOT NULL" in sql
    assert "CREATE TABLE alembic_version" in sql


def test_initial_migration_renders_downgrade(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://localhost/simple_rag"
    )
    config = Config("alembic.ini")

    command.downgrade(config, "head:base", sql=True)

    assert "DROP TABLE documents" in capsys.readouterr().out
