"""Маршруты заявок — ядро жизненного цикла участия в конференции.

Разграничение доступа:

* организатор — видит и изменяет все заявки, принимает решения;
* участник и докладчик — видят только свои заявки и работают только с ними;
* рецензент — видит список заявок для контекста, но не изменяет их.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import auth, models, schemas, services
from app.database import get_db
from app.routers.deps import conflict, not_found, paginate
from app.services import DomainError

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])

require_authenticated = auth.require_authenticated
require_own_application = auth.require_any_permission("application:create", "application:read_own")
require_decide = auth.require_permission("application:decide")


def _is_organizer(user: models.User) -> bool:
    return auth.has_permission(user, "application:decide")


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


def _ensure_can_touch(user: models.User, application: models.Application) -> None:
    """Разрешить работу с заявкой только её автору или организатору."""
    if _is_organizer(user):
        return
    if user.participant_id != application.participant_id:
        raise conflict(
            "forbidden_not_owner",
            "Заявка принадлежит другому участнику: работать с ней может только её автор или организатор",
            http_status=status.HTTP_403_FORBIDDEN,
        )


@router.get("", response_model=schemas.Page[schemas.ApplicationOut], summary="Список заявок")
def list_applications(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_authenticated),
    conference_id: int | None = Query(None, gt=0),
    section_id: int | None = Query(None, gt=0),
    participant_id: int | None = Query(None, gt=0),
    app_status: models.ApplicationStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.ApplicationOut]:
    stmt = select(models.Application).order_by(models.Application.created_at.desc())

    # Организатор и рецензент видят все заявки, остальные — только свои.
    if _is_organizer(user) or auth.has_permission(user, "application:read_all"):
        if participant_id is not None:
            stmt = stmt.where(models.Application.participant_id == participant_id)
    else:
        if user.participant_id is None:
            return schemas.Page[schemas.ApplicationOut](items=[], total=0, limit=limit, offset=offset)
        stmt = stmt.where(models.Application.participant_id == user.participant_id)

    if conference_id is not None:
        stmt = stmt.where(models.Application.conference_id == conference_id)
    if section_id is not None:
        stmt = stmt.where(models.Application.section_id == section_id)
    if app_status is not None:
        stmt = stmt.where(models.Application.status == app_status)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.ApplicationOut)


@router.post(
    "",
    response_model=schemas.ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заявку (черновик)",
    description=(
        "Участник и докладчик создают заявку только от своего имени. Организатор "
        "может создать заявку для любого участника."
    ),
)
def create_application(
    payload: schemas.ApplicationCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_own_application),
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

    participant_id = payload.participant_id
    if not _is_organizer(user):
        if user.participant_id is None:
            raise conflict(
                "no_participant_profile",
                "Учётная запись не связана с участником конференции",
                http_status=status.HTTP_403_FORBIDDEN,
            )
        if participant_id != user.participant_id:
            raise conflict(
                "forbidden_foreign_participant",
                "Заявку можно подать только от своего имени",
                http_status=status.HTTP_403_FORBIDDEN,
            )

    participant = db.get(models.Participant, participant_id)
    if participant is None:
        raise not_found("Участник", participant_id)

    duplicate = db.execute(
        select(models.Application).where(
            models.Application.conference_id == payload.conference_id,
            models.Application.section_id == payload.section_id,
            models.Application.participant_id == participant_id,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise conflict(
            "application_duplicate",
            "Участник уже имеет заявку в этой секции данной конференции",
        )

    data = payload.model_dump()
    data["participant_id"] = participant_id
    application = models.Application(**data)
    if application.needs_hotel and application.format == models.ParticipationFormat.ONLINE:
        raise conflict(
            "hotel_not_allowed_for_online",
            "Дистанционный формат участия не предполагает потребности в гостинице",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    db.add(application)
    services.log_action(
        db,
        entity="application",
        entity_id=None,
        action="create",
        details=f"{application.topic} — создал {user.email}",
    )
    db.commit()
    db.refresh(application)
    return application


@router.get("/{application_id}", response_model=schemas.ApplicationOut, summary="Заявка по id")
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_authenticated),
) -> models.Application:
    application = _load(db, application_id)
    if not (_is_organizer(user) or auth.has_permission(user, "application:read_all")):
        _ensure_can_touch(user, application)
    return application


@router.patch(
    "/{application_id}",
    response_model=schemas.ApplicationOut,
    summary="Изменить черновик заявки",
)
def update_application(
    application_id: int,
    payload: schemas.ApplicationUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_own_application),
) -> models.Application:
    application = _load(db, application_id)
    _ensure_can_touch(user, application)

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


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить черновик заявки",
)
def delete_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_own_application),
) -> None:
    application = _load(db, application_id)
    _ensure_can_touch(user, application)

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
def submit_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_own_application),
) -> models.Application:
    application = _load(db, application_id)
    _ensure_can_touch(user, application)
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
    summary="Принять решение по заявке (только организатор)",
    description=(
        "При принятии заявки автоматически начисляется оргвзнос и приглашение ставится в очередь рассылки."
    ),
)
def decide_application(
    application_id: int,
    payload: schemas.ApplicationDecision,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_decide),
) -> models.Application:
    application = _load(db, application_id)
    try:
        services.decide_application(db, application, accept=payload.accept, comment=payload.comment)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(application)
    return application


@router.post(
    "/{application_id}/withdraw",
    response_model=schemas.ApplicationOut,
    summary="Отозвать заявку",
)
def withdraw_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_own_application),
) -> models.Application:
    application = _load(db, application_id)
    _ensure_can_touch(user, application)
    try:
        services.withdraw_application(db, application)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(application)
    return application
