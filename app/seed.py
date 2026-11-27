"""Наполнение базы данных: демонстрационные данные и две учётные записи.

В системе две роли: администратор (все разделы и служебные страницы) и участник
(только свои заявки, оргвзносы, гостиница и тезисы). Обе учётные записи
создаются при старте.

Модуль идемпотентен: повторный запуск не создаёт дубликатов.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import func, select, update

from app import models
from app.config import get_settings
from app.database import session_scope

logger = logging.getLogger("conference.seed")

DEMO_SLUG = "devops-conf-2026"

# Служебные и зарезервированные зоны, которые не проходят проверку формата
# e-mail: адреса из этих зон нельзя отдавать в API.
LEGACY_EMAIL_DOMAINS = frozenset({"local", "localhost", "internal", "invalid", "test"})

FALLBACK_ADMIN_EMAIL = "admin@example.com"
FALLBACK_PARTICIPANT_EMAIL = "participant@example.com"


def _is_valid_email(value: str) -> bool:
    """Проверить адрес тем же валидатором, что используется в схемах API."""
    try:
        TypeAdapter(EmailStr).validate_python(value)
    except Exception:  # noqa: BLE001 - нужен только факт «валиден или нет»
        return False
    return True


def _safe_email(value: str, fallback: str) -> str:
    """Адрес из настроек, приведённый к корректному виду.

    Служебные зоны (``.local``, ``.internal``, ``.localhost``) не проходят
    проверку ``EmailStr``: такой адрес нельзя ни сохранить, ни выдать в API.
    Поэтому он заменяется на корректный адрес из домена ``example.com``.
    """
    email = (value or "").strip().lower()
    if not _is_valid_email(email):
        logger.warning("Адрес %r недопустим (служебная зона), используется %s", value, fallback)
        return fallback
    return email


def seed_database() -> None:
    """Создать демонстрационные данные и обе учётные записи.

    Порядок важен: сначала схема приводится к текущему виду, затем создаются
    демонстрационные участники и данные, и только потом учётные записи.
    """
    from app.database import migrate_legacy_schema

    migrate_legacy_schema()

    settings = get_settings()
    with session_scope() as db:
        if settings.seed_demo_data:
            _ensure_demo_data(db, settings)
        _ensure_accounts(db, settings)


def _ensure_accounts(db, settings) -> None:  # noqa: ANN001
    """Создать обе учётные записи и привести базу ровно к двум записям.

    Обе учётные записи создаются **без** профиля в реестре участников:

    * администратор не участвует в конференции, поэтому не может подать заявку
      и принять её сам у себя;
    * учётная запись участника — универсальная: ФИО и почту участник указывает в
      каждой заявке, поэтому за учётной записью не закреплён конкретный человек.
    """
    admin_email = _safe_email(settings.admin_email, FALLBACK_ADMIN_EMAIL)
    participant_email = _safe_email(settings.participant_email, FALLBACK_PARTICIPANT_EMAIL)

    _ensure_user(
        db,
        email=admin_email,
        password=settings.effective_admin_password,
        role=models.UserRole.ADMIN,
        full_name=settings.admin_full_name,
        participant=None,
    )

    participant_user = _ensure_user(
        db,
        email=participant_email,
        password=settings.effective_participant_password,
        role=models.UserRole.PARTICIPANT,
        full_name=settings.participant_full_name,
        participant=None,
    )
    # База предыдущей версии могла держать учётную запись привязанной к одному
    # человеку. Универсальная учётная запись ни к кому не привязана: участник
    # каждой заявки определяется её собственными данными.
    if participant_user.participant_id is not None:
        participant_user.participant_id = None

    _own_existing_applications(db, participant_user)
    _remove_other_accounts(db, {admin_email, participant_email})


def _own_existing_applications(db, user) -> None:  # noqa: ANN001
    """Закрепить уже существующие заявки за универсальной учётной записью.

    Демонстрационные заявки создаются наполнением базы и владельца не имеют.
    Учётная запись участника одна, поэтому такие заявки становятся её данными —
    иначе раздел «Мои заявки» оказался бы пустым.
    """
    result = db.execute(
        update(models.Application)
        .where(models.Application.created_by_user_id.is_(None))
        .values(created_by_user_id=user.id)
    )
    if result.rowcount:
        logger.info("Закреплено заявок за универсальной учётной записью: %s", result.rowcount)


def _ensure_user(  # noqa: ANN001
    db,
    *,
    email: str,
    password: str,
    role: models.UserRole,
    full_name: str,
    participant: models.Participant | None,
) -> models.User:
    """Создать или исправить учётную запись.

    Если пароль в базе отличается от текущей настройки, хеш приводится к ней:
    иначе после смены переменной окружения вход работал бы со старым паролем.
    """
    from app import auth

    existing = auth.find_user(db, email)
    if existing is not None:
        existing.role = role
        existing.full_name = full_name
        if participant is not None:
            existing.participant_id = participant.id
        if not existing.is_active:
            existing.is_active = True
        if not auth.verify_password(password, existing.password_hash):
            existing.password_hash = auth.hash_password(password)
            logger.info("Пароль учётной записи %s приведён к значению из настроек", email)
        return existing

    user = auth.create_user(
        db,
        email=email,
        password=password,
        role=role,
        full_name=full_name,
        participant=participant,
    )
    db.add(user)
    # Идентификатор нужен сразу: он используется при закреплении демонстрационных
    # заявок за универсальной учётной записью.
    db.flush()
    logger.info("Создана учётная запись %s (%s)", email, role.value)
    return user


def _remove_other_accounts(db, emails: set[str]) -> None:  # noqa: ANN001
    """Удалить все учётные записи, кроме администратора и участника.

    База, созданная предыдущей версией приложения, могла содержать другие
    учётные записи: они удаляются, чтобы состояние базы совпадало с текущей
    схемой доступа. Вместе с учётной записью каскадом удаляются её сессии.
    """
    others = list(db.execute(select(models.User).where(models.User.email.notin_(emails))).scalars())
    for user in others:
        logger.info("Удалена лишняя учётная запись: %s", user.email)
        db.delete(user)
    if others:
        logger.info("Всего удалено учётных записей: %s", len(others))


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

    # Реестр участников: роли здесь больше нет — как отдельная сущность она ни
    # на что не влияла. Роль есть только у учётной записи (администратор либо
    # участник) и определяет доступ к разделам приложения.
    participants = [
        models.Participant(
            full_name="Иванов Иван Иванович",
            email="ivanov@example.com",
            organization="Московский Политех",
            position="Студент",
            city="Москва",
        ),
        models.Participant(
            full_name="Петрова Анна Сергеевна",
            email="petrova@example.com",
            organization="Московский Политех",
            position="Студент",
            city="Москва",
        ),
        models.Participant(
            full_name="Казарян Михаил Ашотович",
            email="kazaryan@example.com",
            organization="Московский Политех",
            position="Студент",
            city="Москва",
        ),
        models.Participant(
            full_name="Сидоров Пётр Алексеевич",
            email="sidorov@example.com",
            organization="НИУ ВШЭ",
            position="Аналитик",
            city="Санкт-Петербург",
        ),
        models.Participant(
            full_name="Кузнецова Ольга Дмитриевна",
            email="kuznetsova@example.com",
            organization="МГТУ им. Н.Э. Баумана",
            position="Доцент",
            academic_degree="к.т.н.",
            city="Москва",
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
