"""Удаление кэшей и виртуального окружения.

Заменяет команды ``rm -rf`` и ``find``, которых нет в Windows.

Запуск:
    python scripts/make_clean.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DIRECTORIES = [
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "_work/.cache",
    "htmlcov",
]

FILES = [".coverage", "coverage.xml"]


def main() -> int:
    removed: list[str] = []

    for name in DIRECTORIES:
        path = ROOT / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(name)

    for name in FILES:
        path = ROOT / name
        if path.exists():
            path.unlink(missing_ok=True)
            removed.append(name)

    # Каталоги __pycache__ по всему проекту
    for path in ROOT.rglob("__pycache__"):
        if ".venv" in path.parts or ".git" in path.parts:
            continue
        shutil.rmtree(path, ignore_errors=True)

    if removed:
        print("Удалено: " + ", ".join(removed))
    else:
        print("Нечего удалять — каталоги кэшей и виртуальное окружение отсутствуют")
    return 0


if __name__ == "__main__":
    sys.exit(main())
