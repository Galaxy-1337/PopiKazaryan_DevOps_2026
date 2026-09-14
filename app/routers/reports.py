"""Отчётные маршруты: сводки для рассылок и планирования гостиницы."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas, schemas_reports
from app.database import get_db
from app.models import utcnow
from app.routers.deps import not_found

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _count_by(db: Session, column, model, *filters: object) -> dict[str, int]:  # noqa: ANN001
    stmt = select(column, func.count()).select_from(model)
    for condition in filters:
        stmt = stmt.where(condition)
    stmt = stmt.group_by(column)
    result: dict[str, int] = {}
    for value, count in db.execute(stmt):
        key = value.value if hasattr(value, "value") else str(value)
        result[key] = int(count)
    return result


@router.get(
    "/conference/{conference_id}",
    response_model=schemas.ReportOut,
    summary="Сводный отчёт по конференции",
    description=(
        "Используется для очередей рассылки приглашений, контроля оргвзносов "
        "и планирования потребности в гостинице."
    ),
)
def conference_report(conference_id: int, db: Session = Depends(get_db)) -> schemas.ReportOut:
    conference = db.get(models.Conference, conference_id)
    if conference is None:
        raise not_found("Конференция", conference_id)

    application_ids = select(models.Application.id).where(models.Application.conference_id == conference_id)

    applications_total = int(
        db.execute(
            select(func.count())
            .select_from(models.Application)
            .where(models.Application.conference_id == conference_id)
        ).scalar_one()
    )
    participants_total = int(
        db.execute(
            select(func.count(func.distinct(models.Application.participant_id))).where(
                models.Application.conference_id == conference_id
            )
        ).scalar_one()
    )

    fees_total = db.execute(
        select(func.coalesce(func.sum(models.Fee.amount), 0)).where(
            models.Fee.application_id.in_(application_ids)
        )
    ).scalar_one()
    fees_paid = db.execute(
        select(func.coalesce(func.sum(models.Fee.amount), 0)).where(
            models.Fee.application_id.in_(application_ids),
            models.Fee.status == models.FeeStatus.PAID,
        )
    ).scalar_one()

    theses_total = int(
        db.execute(
            select(func.count())
            .select_from(models.Thesis)
            .where(models.Thesis.application_id.in_(application_ids))
        ).scalar_one()
    )

    hotel_bookings_total = int(
        db.execute(
            select(func.count())
            .select_from(models.HotelBooking)
            .where(models.HotelBooking.application_id.in_(application_ids))
        ).scalar_one()
    )
    hotel_guests_total = int(
        db.execute(
            select(func.coalesce(func.sum(models.HotelBooking.guests_count), 0)).where(
                models.HotelBooking.application_id.in_(application_ids),
                models.HotelBooking.status != models.HotelStatus.CANCELLED,
            )
        ).scalar_one()
    )

    return schemas.ReportOut(
        conference_id=conference.id,
        conference_title=conference.title,
        applications_total=applications_total,
        applications_by_status=_count_by(
            db,
            models.Application.status,
            models.Application,
            models.Application.conference_id == conference_id,
        ),
        participants_total=participants_total,
        fees_total_amount=Decimal(str(fees_total)),
        fees_paid_amount=Decimal(str(fees_paid)),
        fees_by_status=_count_by(
            db, models.Fee.status, models.Fee, models.Fee.application_id.in_(application_ids)
        ),
        theses_total=theses_total,
        theses_by_status=_count_by(
            db,
            models.Thesis.status,
            models.Thesis,
            models.Thesis.application_id.in_(application_ids),
        ),
        invitations_by_status=_count_by(
            db,
            models.Invitation.status,
            models.Invitation,
            models.Invitation.application_id.in_(application_ids),
        ),
        hotel_bookings_total=hotel_bookings_total,
        hotel_guests_total=hotel_guests_total,
        hotel_by_status=_count_by(
            db,
            models.HotelBooking.status,
            models.HotelBooking,
            models.HotelBooking.application_id.in_(application_ids),
        ),
        generated_at=utcnow(),
    )


@router.get(
    "/invitations-queue",
    response_model=schemas_reports.InvitationQueueOut,
    summary="Очередь неотправленных приглашений",
)
def invitations_queue(
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
) -> schemas_reports.InvitationQueueOut:
    """Готовая очередь рассылки: приглашения со статусом queued или failed."""
    stmt = (
        select(models.Invitation, models.Participant)
        .join(models.Participant, models.Participant.id == models.Invitation.participant_id)
        .where(models.Invitation.status.in_((models.InvitationStatus.QUEUED, models.InvitationStatus.FAILED)))
        .order_by(models.Invitation.queued_at)
        .limit(limit)
    )
    items = [
        schemas_reports.InvitationQueueItem(
            invitation_id=invitation.id,
            status=invitation.status.value,
            attempts=invitation.attempts,
            email=participant.email,
            full_name=participant.full_name,
            subject=invitation.subject,
        )
        for invitation, participant in db.execute(stmt)
    ]
    return schemas_reports.InvitationQueueOut(items=items, total=len(items))


@router.get(
    "/mailing-list/{conference_id}",
    response_model=schemas_reports.MailingListOut,
    summary="Список рассылки по организациям",
    description=(
        "Возвращает участников принятых заявок, сгруппированных по организациям. "
        "Отчёт предназначен для централизованной рассылки приглашений: оргкомитет "
        "направляет письмо в организацию, а не каждому участнику отдельно."
    ),
)
def mailing_list(conference_id: int, db: Session = Depends(get_db)) -> schemas_reports.MailingListOut:
    conference = db.get(models.Conference, conference_id)
    if conference is None:
        raise not_found("Конференция", conference_id)

    stmt = (
        select(models.Participant)
        .join(models.Application, models.Application.participant_id == models.Participant.id)
        .where(
            models.Application.conference_id == conference_id,
            models.Application.status == models.ApplicationStatus.ACCEPTED,
            models.Participant.is_active.is_(True),
        )
        .order_by(models.Participant.organization, models.Participant.full_name)
        .distinct()
    )

    grouped: dict[str, list[str]] = {}
    for participant in db.execute(stmt).scalars():
        organization = (participant.organization or "Организация не указана").strip()
        grouped.setdefault(organization, []).append(participant.email)

    items = [
        schemas_reports.MailingListEntry(
            organization=organization,
            participants=len(emails),
            emails=sorted(emails),
        )
        for organization, emails in sorted(grouped.items())
    ]

    return schemas_reports.MailingListOut(
        conference_id=conference.id,
        organizations_total=len(items),
        recipients_total=sum(item.participants for item in items),
        items=items,
    )
