"""Apply migrations (create or update the database schema).

The project relies on SQLAlchemy metadata: ``create_all`` creates missing tables
and indexes without touching existing data. For production use, connect Alembic
(see README, section "Development").

Console output is ASCII-only: Windows consoles decode program output using the
system code page, so non-ASCII text would be displayed as garbage.

Run:
    python -m scripts.migrate
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import inspect

from app.config import get_settings
from app.database import create_all, engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate")


def main() -> int:
    settings = get_settings()
    logger.info("Applying schema to database: %s", settings.safe_database_url)

    inspector = inspect(engine)
    before = set(inspector.get_table_names())

    create_all()

    inspector = inspect(engine)
    after = set(inspector.get_table_names())

    created = sorted(after - before)
    if created:
        logger.info("Created tables: %s", ", ".join(created))
    else:
        logger.info("Schema is up to date, nothing to change")
    logger.info("Total tables: %s - %s", len(after), ", ".join(sorted(after)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
