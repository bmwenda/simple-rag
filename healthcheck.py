"""Read-only database health check for deployment probes."""

import sys

from src.config import database_url_from_env
from src.database import check_database_health
from src.domain import ConfigurationError


def main() -> int:
    try:
        check_database_health(database_url_from_env())
    except ConfigurationError as error:
        print(f"Database health check failed: {error}", file=sys.stderr)
        return 1
    print("Database healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
