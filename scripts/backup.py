"""Create a database backup.

* SQLite - the database file is copied.
* PostgreSQL - ``pg_dump`` is called (plain SQL).

Backups are stored in the ``backups/`` directory, which is excluded from Git.

Console output is ASCII-only: Windows consoles decode program output using the
system code page, so non-ASCII text would be displayed as garbage.

Run:
    python -m scripts.backup
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 - pg_dump invocation is intentional
import sys
from datetime import datetime
from pathlib import Path

from app.config import get_settings

BACKUP_DIR = Path("backups")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backup_sqlite() -> Path:
    settings = get_settings()
    source = Path(settings.database_url.split("///", 1)[-1])
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"conference-{_timestamp()}.db"
    shutil.copy2(source, target)
    return target


def backup_postgres() -> Path:
    settings = get_settings()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"conference-{_timestamp()}.sql"

    # postgresql+psycopg2://user:password@host:port/dbname
    url = settings.database_url
    credentials, hostpart = url.split("://", 1)[1].split("@", 1)
    user, _, password = credentials.partition(":")
    hostport, _, dbname = hostpart.partition("/")
    host, _, port = hostport.partition(":")

    command = [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "-h",
        host or "127.0.0.1",
        "-p",
        port or "5432",
        "-U",
        user,
        "-d",
        dbname,
        "-f",
        str(target),
    ]
    result = subprocess.run(command, env={"PGPASSWORD": password}, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError("pg_dump failed")
    return target


def main() -> int:
    settings = get_settings()
    target = backup_sqlite() if settings.is_sqlite else backup_postgres()
    size_kb = target.stat().st_size / 1024
    print(f"Backup created: {target} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
