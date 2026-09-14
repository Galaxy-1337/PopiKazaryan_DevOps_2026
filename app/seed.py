"""Наполнение базы данных: демонстрационные данные и учётная запись администратора.

Модуль идемпотентен: повторный запуск не создаёт дубликатов.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import func, select

from app import models
from app.config import get_settings
from app.database import session_scope

logger = logging.getLogger("conference.seed")

DEMO_SLUG = "devops-conf-2026"

# Служебные и зарезервированные зоны, которые не проходят проверку формата
# e-mail: адреса из этих зон нельзя отдавать в API.
LEGACY_EMAIL_DOMAINS = frozenset({"local", "localhost", "internal", "invalid", "test"})


def _is_valid_email(value: str) -> bool:
    """Проверить адрес тем же валидатором, что используется в схемах API."""
    try:
        TypeAdapter(EmailStr).validate_python(value)
    except Exception:  # noqa: BLE001 - нужен только факт «валиден или нет»
        return False
    return True


def seed_database() -> None:
    """Создать администратора и (при необходимости) демонстрационные данные."""
    settings = get_settings()
    with session_scope() as db:
        _ensure_admin(db)
        if settings.seed_demo_data:
            _ensure_demo_data(db, settings)


def _ensure_admin(db) -> None:  # noqa: ANN001
    """Создать или исправить учётную запись администратора.

    Адрес администратора должен проходить проверку формата e-mail. Если в
    настройках или в базе остался адрес из служебной зоны (``.local``,
    ``.internal``, ``.localhost``), он заменяется на корректный: такие адреса
    не проходят проверку EmailStr, из-за чего выдача списка участников падала
    бы с ошибкой 500.
    """
    settings = get_settings()
    email = settings.admin_email.strip().lower()

    if not _is_valid_email(email):
        fallback = "admin@example.com"
        logger.warning(
            "ADMIN_EMAIL=%s не является допустимым адресом (%s), используется %s",
            settings.admin_email,
            "служебная зона",
            fallback,
        )
        email = fallback

    # Все организаторы: ищем записи с адресом, который не пройдёт проверку
    # формата (например, admin@conference.local), и приводим их к корректному.
    organizers = list(
        db.execute(
            select(models.Participant).where(models.Participant.role == models.ParticipantRole.ORGANIZER)
        ).scalars()
    )

    correct_exists = any(participant.email == email for participant in organizers)
    for participant in organizers:
        if participant.email == email:
            continue
        if not _is_valid_email(participant.email):
            if correct_exists:
                # Дубликат администратора со «сломанным» адресом — удаляем.
                logger.warning("Удалён дубликат администратора с недопустимым адресом %s", participant.email)
                db.delete(participant)
                continue
            logger.info("Исправлен адрес администратора: %s -> %s", participant.email, email)
            participant.email = email
            participant.full_name = settings.admin_full_name
            correct_exists = True
            continue
        if participant.email == email:
            correct_exists = True

    if correct_exists:
        return

    db.add(
        models.Participant(
            full_name=settings.admin_full_name,
            email=email,
            organization="Московский Политех",
            position="Администратор системы",
            city="Москва",
            role=models.ParticipantRole.ORGANIZER,
        )
    )
    logger.info("Создан администратор %s", email)


def _ensure_demo_data(db, settings) -> None:  # noqa: ANN001
    exists = db.execute(
        select(models.Conference).where(models.Conference.slug == DEMO_SLUG)
    ).scalar_one_or_none()
    if exists is not None:
        return

    today = date.today()
    starts_on = today + timedelta(days=45)
    ends_on = starts_on + timedelta(days=2)

    conference = models.Conference(
        title="Методология и практики DevOps",
        slug=DEMO_SLUG,
        description=(
            "Ежегодная конференция по методологии и практикам DevOps: "
            "контейнеризация, CI/CD, наблюдаемость, инженерная культура."
        ),
        starts_on=starts_on,
        ends_on=ends_on,
        location="Москва, Большая Семёновская, 38",
        fee_amount=Decimal("3500.00"),
        is_active=True,
    )
    db.add(conference)
    db.flush()

    sections = [
        models.Section(
            conference_id=conference.id,
            title="CI/CD и автоматизация релизов",
            description="Пайплайны сборки, тестирования и доставки изменений.",
            capacity=settings.section_capacity,
        ),
        models.Section(
            conference_id=conference.id,
            title="Контейнеризация и оркестрация",
            description="Docker, Kubernetes, управление конфигурацией.",
            capacity=settings.section_capacity,
        ),
        models.Section(
            conference_id=conference.id,
            title="Наблюдаемость и надёжность",
            description="Метрики, логи, трассировки, SLO и инциденты.",
            capacity=settings.section_capacity,
        ),
    ]
    db.add_all(sections)
    db.flush()

    participants = [
        models.Participant(
            full_name="Иванов Иван Иванович",
            email="ivanov@example.com",
            organization="Московский Политех",
            position="Студент",
            city="Москва",
            role=models.ParticipantRole.SPEAKER,
        ),
        models.Participant(
            full_name="Петрова Анна Сергеевна",
            email="petrova@example.com",
            organization="Московский Политех",
            position="Студент",
            city="Москва",
            role=models.ParticipantRole.SPEAKER,
        ),
        models.Participant(
            full_name="Казарян Михаил Ашотович",
            email="kazaryan@example.com",
            organization="Московский Политех",
            position="Студент",
            city="Москва",
            role=models.ParticipantRole.SPEAKER,
        ),
        models.Participant(
            full_name="Сидоров Пётр Алексеевич",
            email="sidorov@example.com",
            organization="НИУ ВШЭ",
            position="Аналитик",
            city="Санкт-Петербург",
            role=models.ParticipantRole.LISTENER,
        ),
        models.Participant(
            full_name="Кузнецова Ольга Дмитриевна",
            email="kuznetsova@example.com",
            organization="МГТУ им. Н.Э. Баумана",
            position="Доцент",
            academic_degree="к.т.н.",
            city="Москва",
            role=models.ParticipantRole.REVIEWER,
        ),
    ]
    db.add_all(participants)
    db.flush()

    application_1 = models.Application(
        conference_id=conference.id,
        section_id=sections[0].id,
        participant_id=participants[0].id,
        topic="Автоматизация релизов: от ручных выкладок к GitOps",
        annotation="В докладе рассматривается переход от ручных выкладок к GitOps-подходу.",
        format=models.ParticipationFormat.OFFLINE,
        needs_hotel=True,
    )
    application_2 = models.Application(
        conference_id=conference.id,
        section_id=sections[1].id,
        participant_id=participants[1].id,
        topic="Сравнение подходов к оркестрации контейнеров",
        annotation="Сравнение Docker Compose, Kubernetes и Nomad для учебных проектов.",
        format=models.ParticipationFormat.OFFLINE,
        needs_hotel=False,
    )
    application_3 = models.Application(
        conference_id=conference.id,
        section_id=sections[2].id,
        participant_id=participants[3].id,
        topic="Метрики SLO для студенческих сервисов",
        annotation="Практика внедрения SLO и алертинга в небольших командах.",
        format=models.ParticipationFormat.ONLINE,
        needs_hotel=False,
    )
    db.add_all([application_1, application_2, application_3])
    db.flush()

    # Заявка №1 — доведена до принятия: взнос начислен, приглашение в очереди.
    application_1.status = models.ApplicationStatus.SUBMITTED
    application_1.submitted_at = models.utcnow()
    db.flush()
    from app import services

    services.decide_application(
        db, application_1, accept=True, comment="Доклад соответствует тематике секции"
    )
    db.flush()
    services.create_hotel_booking(
        db,
        application_1,
        hotel_name="Гостиница «Семёновская»",
        room_type="standard",
        guests_count=1,
        check_in=starts_on,
        check_out=ends_on,
    )

    # Заявка №2 — принята без гостиницы.
    application_2.status = models.ApplicationStatus.SUBMITTED
    application_2.submitted_at = models.utcnow()
    db.flush()
    services.decide_application(db, application_2, accept=True, comment="Принято")

    # Заявка №3 — в статусе «подана», ожидает решения.
    application_3.status = models.ApplicationStatus.SUBMITTED
    application_3.submitted_at = models.utcnow()

    db.flush()

    # Тезисы по первой заявке.
    thesis = models.Thesis(
        application_id=application_1.id,
        title="Автоматизация релизов: от ручных выкладок к GitOps",
        abstract=(
            "В работе описан переход команды от ручных выкладок к декларативному "
            "описанию инфраструктуры и непрерывной доставке изменений. Приведены "
            "метрики частоты релизов и времени восстановления после сбоя."
        ),
        keywords="DevOps, GitOps, CI/CD, релиз",
        file_name="thesis_ivanov.pdf",
        file_size_kb=180,
        status=models.ThesisStatus.SUBMITTED,
        submitted_at=models.utcnow(),
    )
    db.add(thesis)
    db.flush()

    total = db.execute(select(func.count(models.Conference.id))).scalar_one()
    logger.info("Демонстрационные данные созданы (конференций в БД: %s)", total)


__all__ = ["DEMO_SLUG", "seed_database"]
