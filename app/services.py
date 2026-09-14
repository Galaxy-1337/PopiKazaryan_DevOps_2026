"""Бизнес-правила предметной области «Конференция».

Здесь сосредоточены правила, которые нельзя (или неудобно) выражать только
средствами СУБД:

* допустимые переходы статусов заявки;
* приём заявки — только при открытой секции и наличии свободных мест;
* автоначисление оргвзноса при переводе заявки в статус «принята»;
* постановка приглашения в очередь рассылки после принятия заявки;
* запрет брони гостиницы для дистанционного формата участия;
* автоматическое истечение неподтверждённой брони;
* запрет приёма тезисов к заявке, которая не принята;
* правила оплаты и возврата оргвзноса.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Application,
    ApplicationStatus,
    AuditLog,
    Conference,
    Fee,
    FeeStatus,
    HotelBooking,
    HotelStatus,
    Invitation,
    InvitationStatus,
    ParticipationFormat,
    Section,
    Thesis,
    ThesisStatus,
    as_aware,
    utcnow,
)

# ---------------------------------------------------------------------------
# Допустимые переходы статусов заявки
# ---------------------------------------------------------------------------
ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: {ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN},
    ApplicationStatus.SUBMITTED: {
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.ACCEPTED: {ApplicationStatus.WITHDRAWN},
    ApplicationStatus.REJECTED: set(),
    ApplicationStatus.WITHDRAWN: set(),
}

STATUS_TITLES: dict[ApplicationStatus, str] = {
    ApplicationStatus.DRAFT: "черновик",
    ApplicationStatus.SUBMITTED: "подана",
    ApplicationStatus.ACCEPTED: "принята",
    ApplicationStatus.REJECTED: "отклонена",
    ApplicationStatus.WITHDRAWN: "отозвана",
}

ACTIVE_SECTION_STATUSES = (ApplicationStatus.SUBMITTED, ApplicationStatus.ACCEPTED)

# Вместимость секции по умолчанию, если значение не задано в конференции.
DEFAULT_SECTION_CAPACITY = 5
# Минимальная вместимость секции: меньше одного места она иметь не может.
MIN_SECTION_CAPACITY = 1


class DomainError(Exception):
    """Нарушено правило предметной области.

    Обработчики HTTP-слоя преобразуют исключение в ответ 409 Conflict
    с машиночитаемым кодом.
    """

    def __init__(self, message: str, *, code: str = "domain_rule_violation", status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def log_action(
    db: Session,
    *,
    entity: str,
    entity_id: int | None,
    action: str,
    details: str | None = None,
) -> AuditLog:
    """Записать действие в журнал (без коммита — коммитит вызывающая сторона)."""
    entry = AuditLog(entity=entity, entity_id=entity_id, action=action, details=details)
    db.add(entry)
    return entry


def can_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    """Проверить допустимость перехода статуса заявки."""
    return target in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(current: ApplicationStatus, target: ApplicationStatus) -> None:
    """Проверить переход статуса и выбросить DomainError при нарушении."""
    if current == target:
        raise DomainError(
            f"Заявка уже находится в статусе «{STATUS_TITLES[current]}»",
            code="status_already_set",
        )
    if not can_transition(current, target):
        raise DomainError(
            f"Недопустимый переход статуса заявки: «{STATUS_TITLES[current]}» → «{STATUS_TITLES[target]}»",
            code="invalid_status_transition",
        )


def section_load(db: Session, section_id: int) -> int:
    """Текущая загрузка секции: число заявок в статусах «подана» и «принята»."""
    stmt = (
        select(func.count(Application.id))
        .where(Application.section_id == section_id)
        .where(Application.status.in_(ACTIVE_SECTION_STATUSES))
    )
    return int(db.execute(stmt).scalar_one())


def assert_section_has_free_seats(
    db: Session, section: Section, *, exclude_application_id: int | None = None
) -> None:
    """Правило: приём заявки невозможен, если секция заполнена.

    Место освобождается при отклонении/отзыве заявки.
    """
    if not section.is_open:
        raise DomainError(
            f"Секция «{section.title}» закрыта для приёма заявок",
            code="section_closed",
        )
    stmt = (
        select(func.count(Application.id))
        .where(Application.section_id == section.id)
        .where(Application.status.in_(ACTIVE_SECTION_STATUSES))
    )
    if exclude_application_id is not None:
        stmt = stmt.where(Application.id != exclude_application_id)
    taken = int(db.execute(stmt).scalar_one())
    if taken >= section.capacity:
        raise DomainError(
            f"В секции «{section.title}» нет свободных мест ({taken} из {section.capacity} занято)",
            code="section_capacity_exceeded",
        )


def assert_conference_accepts_applications(conference: Conference) -> None:
    """Правило: заявки принимаются только по активной конференции."""
    if not conference.is_active:
        raise DomainError(
            f"Приём заявок по конференции «{conference.title}» закрыт",
            code="conference_inactive",
        )


def assert_application_within_conference_dates(conference: Conference, check_in, check_out) -> None:
    """Правило: проживание в гостинице — только в даты проведения конференции."""
    if check_in < conference.starts_on or check_out > conference.ends_on:
        raise DomainError(
            "Даты проживания выходят за период проведения конференции "
            f"({conference.starts_on:%d.%m.%Y} — {conference.ends_on:%d.%m.%Y})",
            code="hotel_dates_out_of_conference",
        )


def assert_hotel_allowed_for_format(application: Application) -> None:
    """Правило: дистанционным участникам гостиница не предоставляется."""
    if application.format == ParticipationFormat.ONLINE:
        raise DomainError(
            "Для дистанционного формата участия бронирование гостиницы недоступно",
            code="hotel_not_allowed_for_online",
        )


def submit_application(db: Session, application: Application) -> Application:
    """Перевести заявку в статус «подана» с проверкой всех правил приёма."""
    assert_transition(application.status, ApplicationStatus.SUBMITTED)
    assert_conference_accepts_applications(application.conference)
    assert_section_has_free_seats(db, application.section, exclude_application_id=application.id)
    application.status = ApplicationStatus.SUBMITTED
    application.submitted_at = utcnow()
    log_action(
        db,
        entity="application",
        entity_id=application.id,
        action="submit",
        details=f"Заявка подана в секцию «{application.section.title}»",
    )
    return application


def decide_application(
    db: Session,
    application: Application,
    *,
    accept: bool,
    comment: str | None = None,
) -> Application:
    """Принять решение по заявке.

    При принятии автоматически:
    * начисляется оргвзнос в размере взноса конференции;
    * приглашение ставится в очередь рассылки.
    """
    target = ApplicationStatus.ACCEPTED if accept else ApplicationStatus.REJECTED
    assert_transition(application.status, target)

    if accept:
        assert_section_has_free_seats(db, application.section, exclude_application_id=application.id)

    application.status = target
    application.decided_at = utcnow()
    application.decision_comment = comment
    log_action(
        db,
        entity="application",
        entity_id=application.id,
        action="accept" if accept else "reject",
        details=comment,
    )

    if accept:
        charge_fee(db, application)
        queue_invitation(db, application)
    return application


def withdraw_application(db: Session, application: Application) -> Application:
    """Отозвать заявку. Возврат взноса выполняется отдельной операцией."""
    assert_transition(application.status, ApplicationStatus.WITHDRAWN)
    application.status = ApplicationStatus.WITHDRAWN
    application.decided_at = utcnow()
    if application.hotel_booking and application.hotel_booking.status in (
        HotelStatus.REQUESTED,
        HotelStatus.CONFIRMED,
    ):
        application.hotel_booking.status = HotelStatus.CANCELLED
    for fee in application.fees:
        if fee.status == FeeStatus.PENDING:
            fee.status = FeeStatus.CANCELLED
    log_action(db, entity="application", entity_id=application.id, action="withdraw")
    return application


def charge_fee(db: Session, application: Application) -> Fee:
    """Начислить оргвзнос по заявке.

    Повторное начисление при наличии незакрытого взноса не создаётся —
    вместо этого обновляется сумма.
    """
    amount: Decimal = application.conference.fee_amount

    existing = next(
        (f for f in application.fees if f.status in (FeeStatus.PENDING, FeeStatus.PAID)),
        None,
    )
    if existing is not None:
        existing.amount = amount
        return existing

    fee = Fee(
        application_id=application.id,
        amount=amount,
        status=FeeStatus.PENDING,
        comment=f"Оргвзнос за участие в конференции «{application.conference.title}»",
    )
    db.add(fee)
    log_action(db, entity="fee", entity_id=application.id, action="charge", details=str(amount))
    return fee


def pay_fee(db: Session, fee: Fee, *, payment_reference: str | None = None) -> Fee:
    """Отметить оргвзнос оплаченным."""
    if fee.status == FeeStatus.PAID:
        raise DomainError("Оргвзнос уже оплачен", code="fee_already_paid")
    if fee.status in (FeeStatus.CANCELLED, FeeStatus.REFUNDED):
        raise DomainError(
            "Нельзя оплатить отменённый или возвращённый оргвзнос",
            code="fee_not_payable",
        )
    if fee.application.status == ApplicationStatus.WITHDRAWN:
        raise DomainError(
            "Нельзя оплатить оргвзнос по отозванной заявке",
            code="fee_for_withdrawn_application",
        )
    fee.status = FeeStatus.PAID
    fee.paid_at = utcnow()
    fee.payment_reference = payment_reference or fee.payment_reference
    log_action(db, entity="fee", entity_id=fee.id, action="pay", details=payment_reference)
    return fee


def refund_fee(db: Session, fee: Fee, *, reason: str | None = None) -> Fee:
    """Вернуть оргвзнос.

    Правило: возврат возможен только для оплаченного взноса и при отозванной
    либо отклонённой заявке.
    """
    if fee.status != FeeStatus.PAID:
        raise DomainError(
            "Возврат возможен только для оплаченного оргвзноса",
            code="fee_not_paid",
        )
    if fee.application.status not in (ApplicationStatus.WITHDRAWN, ApplicationStatus.REJECTED):
        raise DomainError(
            "Возврат оргвзноса возможен только по отозванной или отклонённой заявке",
            code="refund_not_allowed_for_status",
        )
    fee.status = FeeStatus.REFUNDED
    fee.refunded_at = utcnow()
    if reason:
        fee.comment = f"{fee.comment or ''} Возврат: {reason}".strip()
    log_action(db, entity="fee", entity_id=fee.id, action="refund", details=reason)
    return fee


def queue_invitation(db: Session, application: Application) -> Invitation:
    """Поставить приглашение в очередь рассылки (идемпотентно)."""
    if application.invitation is not None:
        return application.invitation

    conference = application.conference
    participant = application.participant
    subject = f"Приглашение на конференцию «{conference.title}»"
    body = (
        f"Уважаемый(ая) {participant.full_name}!\n\n"
        f"Оргкомитет конференции «{conference.title}» приглашает Вас принять участие "
        f"в работе секции «{application.section.title}».\n"
        f"Даты проведения: {conference.starts_on:%d.%m.%Y} — {conference.ends_on:%d.%m.%Y}.\n"
        f"Формат участия: {application.format.value}.\n"
        f"Тема: {application.topic}.\n\n"
        f"Место проведения: {conference.location}.\n"
        "Просим подтвердить участие и оплатить оргвзнос.\n\n"
        "Оргкомитет"
    )
    invitation = Invitation(
        application_id=application.id,
        participant_id=participant.id,
        subject=subject,
        body=body,
        status=InvitationStatus.QUEUED,
    )
    db.add(invitation)
    log_action(
        db,
        entity="invitation",
        entity_id=application.id,
        action="queue",
        details=subject,
    )
    return invitation


def send_invitation(
    db: Session, invitation: Invitation, *, success: bool = True, error: str | None = None
) -> Invitation:
    """Отправить приглашение (в учебном проекте — фиксация факта отправки)."""
    if invitation.status in (InvitationStatus.CANCELLED,):
        raise DomainError("Приглашение отменено и не может быть отправлено", code="invitation_cancelled")
    if invitation.status in (InvitationStatus.SENT, InvitationStatus.DELIVERED):
        raise DomainError("Приглашение уже отправлено", code="invitation_already_sent")

    invitation.attempts += 1
    if success:
        invitation.status = InvitationStatus.SENT
        invitation.sent_at = utcnow()
        invitation.last_error = None
        log_action(db, entity="invitation", entity_id=invitation.id, action="send")
    else:
        invitation.status = InvitationStatus.FAILED
        invitation.last_error = error or "Неизвестная ошибка отправки"
        log_action(
            db,
            entity="invitation",
            entity_id=invitation.id,
            action="send_failed",
            details=invitation.last_error,
        )
    return invitation


def add_thesis(db: Session, application: Application, thesis: Thesis) -> Thesis:
    """Добавить тезисы к заявке.

    Правило: тезисы принимаются только по принятой заявке, а размер файла
    не должен превышать настроенный предел.
    """
    if application.status != ApplicationStatus.ACCEPTED:
        raise DomainError(
            "Тезисы принимаются только по принятой заявке",
            code="thesis_requires_accepted_application",
        )
    settings = get_settings()
    if thesis.file_size_kb is not None and thesis.file_size_kb > settings.abstract_max_size_kb:
        raise DomainError(
            f"Размер файла тезисов превышает {settings.abstract_max_size_kb} КБ",
            code="thesis_file_too_large",
        )
    thesis.application_id = application.id
    thesis.status = ThesisStatus.SUBMITTED
    thesis.submitted_at = utcnow()
    db.add(thesis)
    log_action(db, entity="thesis", entity_id=application.id, action="submit", details=thesis.title)
    return thesis


def review_thesis(
    db: Session,
    thesis: Thesis,
    *,
    reviewer_name: str,
    score: int,
    accepted: bool,
    comment: str | None = None,
) -> Thesis:
    """Зафиксировать результат рецензирования тезисов."""
    if not 1 <= score <= 10:
        raise DomainError("Оценка рецензента должна быть от 1 до 10", code="invalid_review_score")
    if thesis.status not in (ThesisStatus.SUBMITTED, ThesisStatus.UNDER_REVIEW, ThesisStatus.REVISION):
        raise DomainError(
            "Рецензирование возможно только для тезисов, отправленных на рецензию",
            code="thesis_not_reviewable",
        )
    thesis.reviewer_name = reviewer_name
    thesis.review_score = score
    thesis.review_comment = comment
    thesis.reviewed_at = utcnow()
    # Порог 6 баллов — содержательное правило предметной области.
    thesis.status = ThesisStatus.ACCEPTED if (accepted and score >= 6) else ThesisStatus.REJECTED
    log_action(
        db,
        entity="thesis",
        entity_id=thesis.id,
        action="review",
        details=f"Оценка {score}, итог: {thesis.status.value}",
    )
    return thesis


def create_hotel_booking(
    db: Session,
    application: Application,
    *,
    hotel_name: str,
    room_type: str,
    guests_count: int,
    check_in,
    check_out,
) -> HotelBooking:
    """Создать потребность в гостинице.

    Правила: заявка принята, формат участия — не дистанционный, срок
    подтверждения ограничен настройкой ``HOTEL_CONFIRMATION_HOURS``.
    """
    if application.status != ApplicationStatus.ACCEPTED:
        raise DomainError(
            "Бронирование гостиницы доступно только по принятой заявке",
            code="hotel_requires_accepted_application",
        )
    assert_hotel_allowed_for_format(application)
    assert_application_within_conference_dates(application.conference, check_in, check_out)
    if application.hotel_booking is not None and application.hotel_booking.status not in (
        HotelStatus.CANCELLED,
        HotelStatus.EXPIRED,
    ):
        raise DomainError("По заявке уже существует активная бронь гостиницы", code="hotel_booking_exists")

    settings = get_settings()
    booking = HotelBooking(
        application_id=application.id,
        hotel_name=hotel_name,
        room_type=room_type,
        guests_count=guests_count,
        check_in=check_in,
        check_out=check_out,
        status=HotelStatus.REQUESTED,
        confirmation_deadline=utcnow() + timedelta(hours=settings.hotel_confirmation_hours),
    )
    db.add(booking)
    log_action(db, entity="hotel", entity_id=application.id, action="request", details=hotel_name)
    return booking


def confirm_hotel_booking(db: Session, booking: HotelBooking) -> HotelBooking:
    """Подтвердить бронь. Просроченная бронь подтверждена быть не может."""
    if booking.status == HotelStatus.CONFIRMED:
        raise DomainError("Бронь уже подтверждена", code="hotel_already_confirmed")
    if booking.status in (HotelStatus.CANCELLED, HotelStatus.EXPIRED):
        raise DomainError("Нельзя подтвердить отменённую или истёкшую бронь", code="hotel_not_confirmable")
    if as_aware(booking.confirmation_deadline) < utcnow():
        booking.status = HotelStatus.EXPIRED
        raise DomainError("Срок подтверждения брони истёк", code="hotel_confirmation_expired")

    booking.status = HotelStatus.CONFIRMED
    booking.confirmed_at = utcnow()
    log_action(db, entity="hotel", entity_id=booking.id, action="confirm")
    return booking


def expire_stale_hotel_bookings(db: Session) -> int:
    """Пометить просроченные брони как истёкшие. Возвращает число записей."""
    # Сравнение выполняется в Python: SQLite не хранит часовой пояс, поэтому
    # фильтрация в SQL дала бы разные результаты для SQLite и PostgreSQL.
    stmt = select(HotelBooking).where(HotelBooking.status == HotelStatus.REQUESTED)
    now = utcnow()
    expired = 0
    for booking in db.execute(stmt).scalars():
        if as_aware(booking.confirmation_deadline) >= now:
            continue
        booking.status = HotelStatus.EXPIRED
        log_action(db, entity="hotel", entity_id=booking.id, action="expire")
        expired += 1
    return expired


__all__ = [
    "ALLOWED_TRANSITIONS",
    "DomainError",
    "STATUS_TITLES",
    "add_thesis",
    "assert_transition",
    "charge_fee",
    "confirm_hotel_booking",
    "create_hotel_booking",
    "decide_application",
    "expire_stale_hotel_bookings",
    "log_action",
    "pay_fee",
    "queue_invitation",
    "refund_fee",
    "review_thesis",
    "section_load",
    "send_invitation",
    "submit_application",
    "withdraw_application",
]
