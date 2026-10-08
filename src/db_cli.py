"""Local PostgreSQL database commands for development."""

import argparse
import ipaddress
from collections.abc import Sequence
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from .config import database_url_from_env
from .domain import ConfigurationError

_MAINTENANCE_DATABASE = "postgres"
_SYSTEM_DATABASES = {_MAINTENANCE_DATABASE, "template0", "template1"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the local registry database")
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("create", "drop", "migrate", "prepare"):
        subparsers.add_parser(action)
    args = parser.parse_args(argv)

    try:
        if args.action == "create":
            create_database()
        elif args.action == "drop":
            drop_database()
        elif args.action == "migrate":
            upgrade_schema()
        else:
            create_database()
            upgrade_schema()
    except ConfigurationError as error:
        print(error)
        return 1
    except (psycopg.Error, SQLAlchemyError):
        print("Database command failed; check the local PostgreSQL server and settings.")
        return 1

    return 0


def create_database() -> bool:
    """Create the configured local database if it does not already exist."""
    database_url = _local_database_url()
    database_name = _application_database_name(database_url)
    maintenance_url = database_url.set(database=_MAINTENANCE_DATABASE)

    with psycopg.connect(
        maintenance_url.set(drivername="postgresql").render_as_string(
            hide_password=False
        ),
        connect_timeout=5,
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
        ).fetchone()
        if exists:
            print(f"Database {database_name} already exists.")
            return False
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )

    print(f"Created database {database_name}.")
    return True


def drop_database() -> bool:
    """Drop the configured local database after an exact-name confirmation."""
    database_url = _local_database_url()
    database_name = _application_database_name(database_url)
    confirmation = input(f"Type {database_name} to drop this database: ")
    if confirmation != database_name:
        print("Database drop cancelled.")
        return False

    maintenance_url = database_url.set(database=_MAINTENANCE_DATABASE)
    with psycopg.connect(
        maintenance_url.set(drivername="postgresql").render_as_string(
            hide_password=False
        ),
        connect_timeout=5,
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
        ).fetchone()
        if not exists:
            print(f"Database {database_name} does not exist.")
            return False
        connection.execute(
            sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name))
        )

    print(f"Dropped database {database_name}.")
    return True


def upgrade_schema() -> None:
    """Apply all pending registry schema migrations."""
    _application_database_name(_local_database_url())
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(config, "head")
    print("Database schema is up to date.")


def _local_database_url() -> URL:
    database_url = database_url_from_env()
    host = database_url.host
    is_localhost = host is not None and host.casefold() == "localhost"
    if host is not None:
        try:
            is_localhost = is_localhost or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
    has_host_override = any(
        parameter in database_url.query for parameter in ("host", "hostaddr", "service")
    )
    if (
        database_url.drivername != "postgresql+psycopg"
        or not is_localhost
        or has_host_override
    ):
        raise ConfigurationError(
            "Local database commands require a local PostgreSQL URL"
        )
    return database_url


def _application_database_name(database_url: URL) -> str:
    database_name = database_url.database
    if not database_name or database_name in _SYSTEM_DATABASES:
        raise ConfigurationError(
            "DATABASE_URL must name an application database, not a PostgreSQL system database"
        )
    return database_name


if __name__ == "__main__":
    raise SystemExit(main())
