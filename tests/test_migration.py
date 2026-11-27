"""Совместимость со схемой предыдущей версии.

Разграничение доступа убрало роль из реестра участников и сменило набор ролей
учётной записи. Существующая база должна при этом продолжать работать: поля
предыдущей версии удаляются, а прежние значения роли приводятся к новым.
"""

from __future__ import annotations

from sqlalchemy import inspect, select, text

from app import models
from app.database import SessionLocal, engine, migrate_legacy_schema


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _add_legacy_participant_role() -> None:
    """Добавить поле participants.role, как в базе предыдущей версии."""
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE participants ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'LISTENER'")
        )


def test_legacy_participant_role_column_is_removed() -> None:
    """Поле роли в реестре участников удаляется, записи реестра сохраняются."""
    _add_legacy_participant_role()
    assert "role" in _column_names("participants")

    with SessionLocal() as session:
        before = session.execute(select(models.Participant.email)).scalars().all()
    assert before, "наполнение базы должно было создать участников"

    migrate_legacy_schema()

    assert "role" not in _column_names("participants")
    with SessionLocal() as session:
        after = session.execute(select(models.Participant.email)).scalars().all()
    assert sorted(after) == sorted(before), "записи реестра не должны потеряться"


def test_legacy_account_roles_are_mapped() -> None:
    """Прежние роли учётных записей приводятся к ролям администратора и участника."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (email, full_name, role, password_hash, is_active, created_at) "
                "VALUES ('legacy.admin@example.com', 'Прежний организатор', 'ORGANIZER', 'x', 1, "
                "'2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users (email, full_name, role, password_hash, is_active, created_at) "
                "VALUES ('legacy.speaker@example.com', 'Прежний докладчик', 'SPEAKER', 'x', 1, "
                "'2026-01-01 00:00:00')"
            )
        )

    migrate_legacy_schema()

    with SessionLocal() as session:
        admin = session.execute(
            select(models.User).where(models.User.email == "legacy.admin@example.com")
        ).scalar_one()
        speaker = session.execute(
            select(models.User).where(models.User.email == "legacy.speaker@example.com")
        ).scalar_one()

    assert admin.role == models.UserRole.ADMIN
    assert admin.is_admin is True
    assert speaker.role == models.UserRole.PARTICIPANT
    assert speaker.is_admin is False


def test_migration_is_idempotent() -> None:
    """Повторный запуск на актуальной схеме ничего не меняет и не падает."""
    migrate_legacy_schema()
    migrate_legacy_schema()
    assert "role" not in _column_names("participants")
