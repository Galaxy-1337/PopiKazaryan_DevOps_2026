"""Маршруты заявок — ядро жизненного цикла участия в конференции."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas, services
from app.database import get_db
from app.routers.deps import conflict, not_found, paginate
from app.services import DomainError

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


def _load(db: Session, application_id: int) -> models.Application:
    stmt = (
        select(models.Application)
        .options(
            selectinload(models.Application.conference),
            selectinload(models.Application.section),
            selectinload(models.Application.participant),
            selectinload(models.Application.fees),
            selectinload(models.Application.invitation),
            selectinload(models.Application.hotel_booking),
        )
        .where(models.Application.id == application_id)
    )
    application = db.execute(stmt).scalar_one_or_none()
    if application is None:
        raise not_found("Заявка", application_id)
    return application


@router.get("", response_model=schemas.Page[schemas.ApplicationOut], summary="Список заявок")
def list_applications(
    db: Session = Depends(get_db),
    conference_id: int | None = Query(None, gt=0),
    section_id: int | None = Query(None, gt=0),
    participant_id: int | None = Query(None, gt=0),
    app_status: models.ApplicationStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.ApplicationOut]:
    stmt = select(models.Application).order_by(models.Application.created_at.desc())
    if conference_id is not None:
        stmt = stmt.where(models.Application.conference_id == conference_id)
    if section_id is not None:
        stmt = stmt.where(models.Application.section_id == section_id)
    if participant_id is not None:
        stmt = stmt.where(models.Application.participant_id == participant_id)
    if app_status is not None:
        stmt = stmt.where(models.Application.status == app_status)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.ApplicationOut)


@router.post(
    "",
    response_model=schemas.ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заявку (черновик)",
)
def create_application(
    payload: schemas.ApplicationCreate, db: Session = Depends(get_db)
) -> models.Application:
    conference = db.get(models.Conference, payload.conference_id)
    if conference is None:
        raise not_found("Конференция", payload.conference_id)

    section = db.get(models.Section, payload.section_id)
    if section is None:
        raise not_found("Секция", payload.section_id)
    if section.conference_id != conference.id:
        raise conflict(
            "section_not_in_conference",
            "Выбранная секция относится к другой конференции",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    participant = db.get(models.Participant, payload.participant_id)
    if participant is None:
        raise not_found("Участник", payload.participant_id)

    duplicate = db.execute(
        select(models.Application).where(
            models.Application.conference_id == payload.conference_id,
            models.Application.section_id == payload.section_id,
            models.Application.participant_id == payload.participant_id,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise conflict(
            "application_duplicate",
            "Участник уже имеет заявку в этой секции данной конференции",
        )

    application = models.Application(**payload.model_dump())
    if application.needs_hotel and application.format == models.ParticipationFormat.ONLINE:
        raise conflict(
            "hotel_not_allowed_for_online",
            "Дистанционный формат участия не предполагает потребности в гостинице",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    db.add(application)
    services.log_action(db, entity="application", entity_id=None, action="create", details=application.topic)
    db.commit()
    db.refresh(application)
    return application


@router.get("/{application_id}", response_model=schemas.ApplicationOut, summary="Заявка по id")
def get_application(application_id: int, db: Session = Depends(get_db)) -> models.Application:
    return _load(db, application_id)


@router.patch("/{application_id}", response_model=schemas.ApplicationOut, summary="Изменить черновик заявки")
def update_application(
    application_id: int, payload: schemas.ApplicationUpdate, db: Session = Depends(get_db)
) -> models.Application:
    application = _load(db, application_id)
    if application.status != models.ApplicationStatus.DRAFT:
        raise conflict(
            "application_not_editable",
            "Редактировать можно только заявку в статусе «черновик»",
        )

    data = payload.model_dump(exclude_unset=True)
    if "section_id" in data and data["section_id"] is not None:
        section = db.get(models.Section, data["section_id"])
        if section is None:
            raise not_found("Секция", data["section_id"])
        if section.conference_id != application.conference_id:
            raise conflict(
                "section_not_in_conference",
                "Выбранная секция относится к другой конференции",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

    for field, value in data.items():
        setattr(application, field, value)

    if application.needs_hotel and application.format == models.ParticipationFormat.ONLINE:
        raise conflict(
            "hotel_not_allowed_for_online",
            "Дистанционный формат участия не предполагает потребности в гостинице",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    db.commit()
    db.refresh(application)
    return application


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить черновик заявки")
def delete_application(application_id: int, db: Session = Depends(get_db)) -> None:
    application = _load(db, application_id)
    if application.status not in (models.ApplicationStatus.DRAFT, models.ApplicationStatus.WITHDRAWN):
        raise conflict(
            "application_not_deletable",
            "Удалить можно только черновик или отозванную заявку",
        )
    db.delete(application)
    db.commit()


@router.post(
    "/{application_id}/submit",
    response_model=schemas.ApplicationOut,
    summary="Подать заявку",
    description=(
        "Проверяет правила: конференция активна, секция открыта и имеет свободные места. "
        "При нарушении возвращает 409 с кодом правила."
    ),
)
def submit_application(application_id: int, db: Session = Depends(get_db)) -> models.Application:
    application = _load(db, application_id)
    try:
        services.submit_application(db, application)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(application)
    return application


@router.post(
    "/{application_id}/decision",
    response_model=schemas.ApplicationOut,
    summary="Принять решение по заявке",
    description=(
        "При принятии заявки автоматически начисляется оргвзнос и приглашение ставится в очередь рассылки."
    ),
)
def decide_application(
    application_id: int, payload: schemas.ApplicationDecision, db: Session = Depends(get_db)
) -> models.Application:
    application = _load(db, application_id)
    try:
        services.decide_application(db, application, accept=payload.accept, comment=payload.comment)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(application)
    return application


@router.post("/{application_id}/withdraw", response_model=schemas.ApplicationOut, summary="Отозвать заявку")
def withdraw_application(application_id: int, db: Session = Depends(get_db)) -> models.Application:
    application = _load(db, application_id)
    try:
        services.withdraw_application(db, application)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(application)
    return application
