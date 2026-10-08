"""Database URL parsing, connection setup, and health probing."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from .domain import ConfigurationError


def parse_database_url(raw_url: str | None) -> URL:
    if not raw_url:
        raise ConfigurationError("DATABASE_URL is required")
    try:
        url = make_url(raw_url)
    except (SQLAlchemyError, ValueError):
        raise ConfigurationError("DATABASE_URL is invalid") from None
    if url.drivername == "postgresql":
        return url.set(drivername="postgresql+psycopg")
    return url


def create_database_engine(database_url: URL) -> Engine:
    return create_engine(
        database_url,
        connect_args={"connect_timeout": 5},
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
