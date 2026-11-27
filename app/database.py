"""Подключение к базе данных и управление сессиями."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger("conference.database")


class Base(DeclarativeBase):
    """Базовый класс декларативных моделей."""


_settings = get_settings()

if _settings.is_sqlite:
    # Для файловой SQLite создаём каталог, иначе соединение не откроется.
    db_path = _settings.database_url.split("///", 1)[-1]
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

_connect_args = {"check_same_thread": False} if _settings.is_sqlite else {}

engine = create_engine(
    _settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    """Включить контроль внешних ключей в SQLite (по умолчанию выключен)."""
    if _settings.is_sqlite:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI-зависимость: сессия БД на один HTTP-запрос."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Сессия БД с коммитом/откатом — для скриптов и наполнения данными."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def migrate_legacy_schema() -> None:
    """Привести базу предыдущей версии к текущей схеме.

    Разграничение доступа сделало поле ``participants.role`` ненужным: роли в
    реестре участников больше нет, а роль учётной записи принимает значения
    ``admin`` и ``participant``. Здесь база приводится к этому виду **без потери
    данных**, чтобы после обновления не приходилось удалять существующую базу.

    Если схема уже актуальна, функция ничего не делает.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "participants" in tables:
        columns = {column["name"] for column in inspector.get_columns("participants")}
        if "role" in columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE participants DROP COLUMN role"))
                logger.info("Схема обновлена: поле participants.role удалено")
            except DBAPIError as exc:
                logger.warning(
                    "Не удалось удалить поле participants.role (%s). "
                    "Удалите базу (файл data/conference.db либо том PostgreSQL "
                    "командой docker compose down -v) и запустите приложение заново.",
                    exc.__class__.__name__,
                )

    if "users" in tables:
        with engine.begin() as connection:
            # Прежняя роль организатора становится ролью администратора, а все
            # прежние роли участников — ролью участника. SQLAlchemy хранит в базе
            # ИМЕНА элементов перечисления (ORGANIZER, LISTENER, ...), поэтому
            # учитываются оба варианта написания.
            connection.execute(
                text("UPDATE users SET role = 'ADMIN' WHERE role IN ('ORGANIZER', 'organizer')")
            )
            connection.execute(
                text(
                    "UPDATE users SET role = 'PARTICIPANT' "
                    "WHERE role IN ('LISTENER', 'SPEAKER', 'REVIEWER', "
                    "'listener', 'speaker', 'reviewer')"
                )
            )

    if "applications" in tables:
        columns = {column["name"] for column in inspector.get_columns("applications")}
        if "created_by_user_id" not in columns:
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "ALTER TABLE applications ADD COLUMN created_by_user_id INTEGER "
                            "REFERENCES users(id) ON DELETE SET NULL"
                        )
                    )
                logger.info("Схема обновлена: добавлено поле applications.created_by_user_id")
            except DBAPIError as exc:
                logger.warning(
                    "Не удалось добавить поле applications.created_by_user_id (%s). "
                    "Удалите базу (файл data/conference.db либо том PostgreSQL "
                    "командой docker compose down -v) и запустите приложение заново.",
                    exc.__class__.__name__,
                )


def create_all() -> None:
    """Создать схему БД, если она ещё не создана, и обновить её предыдущую версию."""
    from app import models  # noqa: F401  (регистрация моделей в metadata)

    migrate_legacy_schema()
    Base.metadata.create_all(bind=engine)


def drop_all() -> None:
    """Удалить все таблицы (используется в тестах и при сбросе)."""
    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)


__all__ = [
    "Base",
    "SessionLocal",
    "create_all",
    "drop_all",
    "engine",
    "get_db",
    "migrate_legacy_schema",
    "session_scope",
]
