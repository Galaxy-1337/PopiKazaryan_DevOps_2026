"""Создание файла .env из шаблона .env.example, если его ещё нет.

Заменяет команду ``cp``, которой нет в Windows.

Запуск:
    python scripts/make_setup_env.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"


def main() -> int:
    if TARGET.exists():
        print("Файл .env уже существует — оставляю без изменений")
        return 0

    if not EXAMPLE.exists():
        print("Не найден .env.example — пропускаю создание .env", file=sys.stderr)
        return 1

    shutil.copyfile(EXAMPLE, TARGET)
    print("Создан .env из .env.example — проверьте значения (пароль администратора)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
