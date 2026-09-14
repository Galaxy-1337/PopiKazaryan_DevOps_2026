"""Восстановление базы данных из резервной копии.

Запуск:
    python -m scripts.restore backups/conference-20260101-120000.db
    python -m scripts.restore --list
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404
import sys
from pathlib import Path

from app.config import get_settings

BACKUP_DIR = Path("backups")


def list_backups() -> int:
    if not BACKUP_DIR.exists():
        print("Каталог backups/ отсутствует — резервных копий нет")
        return 0
    files = sorted(BACKUP_DIR.iterdir())
    if not files:
        print("Резервных копий нет")
        return 0
    print("Доступные резервные копии:")
    for item in files:
        print(f"  {item}  ({item.stat().st_size / 1024:.1f} КБ)")
    return 0


def restore_sqlite(archive: Path) -> None:
    settings = get_settings()
    target = Path(settings.database_url.split("///", 1)[-1])
    if not archive.exists():
        raise FileNotFoundError(f"Копия не найдена: {archive}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        safety = target.with_suffix(target.suffix + ".before-restore")
        shutil.copy2(target, safety)
        print(f"Текущая база сохранена как {safety}")
    shutil.copy2(archive, target)
    print(f"База восстановлена из {archive} → {target}")


def restore_postgres(archive: Path) -> None:
    settings = get_settings()
    url = settings.database_url
    credentials, hostpart = url.split("://", 1)[1].split("@", 1)
    user, _, password = credentials.partition(":")
    hostport, _, dbname = hostpart.partition("/")
    host, _, port = hostport.partition(":")

    command = [
        "psql",
        "-h",
        host or "127.0.0.1",
        "-p",
        port or "5432",
        "-U",
        user,
        "-d",
        dbname,
        "-f",
        str(archive),
    ]
    result = subprocess.run(command, env={"PGPASSWORD": password}, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError("psql завершился с ошибкой")
    print(f"База восстановлена из {archive}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"--list", "-l"}:
        return list_backups()

    archive = Path(argv[0])
    settings = get_settings()
    if settings.is_sqlite:
        restore_sqlite(archive)
    else:
        restore_postgres(archive)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
