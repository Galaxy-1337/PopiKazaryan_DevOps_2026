"""Создание резервной копии базы данных.

* SQLite — копирование файла базы и снятие логического дампа схемы.
* PostgreSQL — вызов ``pg_dump`` (plain SQL).

Копии складываются в каталог ``backups/`` (исключён из репозитория).

Запуск:
    python -m scripts.backup
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 — вызов pg_dump предусмотрен сценарием
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
        raise FileNotFoundError(f"Файл базы данных не найден: {source}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"conference-{_timestamp()}.db"
    shutil.copy2(source, target)
    return target


def backup_postgres() -> Path:
    settings = get_settings()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"conference-{_timestamp()}.sql"

    url = settings.database_url
    # postgresql+psycopg2://user:password@host:port/dbname
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
    env = {"PGPASSWORD": password}
    result = subprocess.run(command, env={**env}, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError("pg_dump завершился с ошибкой")
    return target


def main() -> int:
    settings = get_settings()
    target = backup_sqlite() if settings.is_sqlite else backup_postgres()
    size_kb = target.stat().st_size / 1024
    print(f"Резервная копия создана: {target} ({size_kb:.1f} КБ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
