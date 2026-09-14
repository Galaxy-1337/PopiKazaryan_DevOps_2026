"""Применение миграций (создание/обновление схемы базы данных).

Проект использует SQLAlchemy Core-метаданные: ``create_all`` создаёт недостающие
таблицы и индексы, не затрагивая существующие данные. Для промышленной
эксплуатации предусмотрено подключение Alembic (см. README, раздел «Развитие»).

Запуск:
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
    logger.info("Применение схемы к БД: %s", settings.safe_database_url)

    inspector = inspect(engine)
    before = set(inspector.get_table_names())

    create_all()

    inspector = inspect(engine)
    after = set(inspector.get_table_names())

    created = sorted(after - before)
    if created:
        logger.info("Созданы таблицы: %s", ", ".join(created))
    else:
        logger.info("Схема уже актуальна, изменений нет")
    logger.info("Всего таблиц: %s — %s", len(after), ", ".join(sorted(after)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
