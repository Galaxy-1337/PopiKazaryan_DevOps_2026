"""Печать списка команд make с описаниями.

Заменяет конструкцию ``grep | awk``, которая не работает на Windows: разбор
Makefile выполняется средствами Python.

Запуск:
    python scripts/make_help.py
"""

from __future__ import annotations

import contextlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"

TARGET_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9_-]*):.*?##\s*(.*)$")


def force_utf8_output() -> None:
    """Выводить текст в UTF-8.

    Консоль Windows по умолчанию декодирует вывод программы в системной
    кодировке, из-за чего русский текст превращается в нечитаемые символы.
    Принудительный UTF-8 решает проблему и в Windows Terminal, и в VS Code.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8")


def main() -> int:
    force_utf8_output()

    if not MAKEFILE.exists():
        print("Makefile не найден", file=sys.stderr)
        return 1

    targets: list[tuple[str, str]] = []
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        match = TARGET_RE.match(line)
        if match:
            targets.append((match.group(1), match.group(2).strip()))

    width = max((len(name) for name, _ in targets), default=10)
    print("Доступные команды:")
    for name, description in targets:
        print(f"  make {name:<{width}}  {description}")
    print()
    print("Примеры:")
    print("  make setup     # один раз: виртуальное окружение, зависимости, .env")
    print("  make run       # локальный запуск на SQLite")
    print("  make verify    # полный набор проверок перед коммитом")
    print("  make up        # запуск в контейнерах (PostgreSQL)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
