"""Database URL validation, connection setup, and health probing."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from .domain import ConfigurationError


def parse_postgres_url(raw_url: str | None) -> URL:
    if not raw_url:
        raise ConfigurationError("DATABASE_URL is required")
    try:
        url = make_url(raw_url)
    except (SQLAlchemyError, ValueError):
        raise ConfigurationError("DATABASE_URL must be a valid PostgreSQL URL") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg"} or not url.database:
        raise ConfigurationError("DATABASE_URL must be a PostgreSQL URL")
    return url.set(drivername="postgresql+psycopg")


def create_database_engine(database_url: URL) -> Engine:
    connect_args = (
        {"connect_timeout": 5}
        if database_url.get_backend_name() == "postgresql"
        else {}
    )
    return create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


def check_database_health(database_url: URL) -> None:
    """Require a successful read-only query; never expose connection details."""
    engine: Engine | None = None
    try:
        engine = create_database_engine(database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, ImportError):
        raise ConfigurationError("Document registry database is unavailable") from None
    finally:
        if engine is not None:
            engine.dispose()
