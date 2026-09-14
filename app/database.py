"""Подключение к базе данных и управление сессиями."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


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


def create_all() -> None:
    """Создать схему БД, если она ещё не создана."""
    from app import models  # noqa: F401  (регистрация моделей в metadata)

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
    "session_scope",
]
