"""Маршруты заявок — ядро жизненного цикла участия в конференции.

Разграничение доступа:

* администратор — видит все заявки и принимает по ним решения (принять или
  отклонить). Сам администратор заявок не подаёт и не может «принять свою
  заявку»: права ``application:create`` у него нет;
* участник — видит и изменяет только заявки, поданные из его учётной записи:
  создаёт черновик, подаёт, отзывает. Чужую заявку он не увидит ни в списке, ни
  по прямому адресу.

Кто именно участвует в конференции, определяется **данными заявки** (ФИО и
электронная почта), а не учётной записью: учётная запись участника
универсальная, поэтому из-под неё можно подать заявки на разных людей. Правило
«один человек — одна заявка в секции» сравнивает участника реестра, найденного
по почте из заявки.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import auth, models, schemas, services
from app.database import get_db
from app.routers.deps import conflict, not_found, paginate
from app.services import DomainError

logger = logging.getLogger("conference.applications")

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])

require_authenticated = auth.require_authenticated
# Заявки подаёт и меняет только участник: администратор работает с ними лишь
# через решения (принять/отклонить).
require_participant = auth.require_participant
require_decide = auth.require_admin


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


def _ensure_owner(user: models.User, application: models.Application) -> None:
    """Работать с заявкой может только учётная запись, из-под которой её подали.

    Администратор сюда не попадает: операции с заявкой доступны лишь роли
    «участник» (см. зависимости маршрутов).
    """
    if application.created_by_user_id != user.id:
        raise conflict(
            "forbidden_not_owner",
            "Заявка подана из другой учётной записи: доступна только её автору",
            http_status=status.HTTP_403_FORBIDDEN,
        )


def _resolve_participant(db: Session, payload: schemas.ApplicationCreate) -> models.Participant:
    """Найти или создать участника по данным заявки.

    Человек определяется почтой из заявки. Если участник с такой почтой уже есть
    в реестре, заявка оформляется на него — правило «один человек — одна заявка в
    секции» сравнивает именно эти данные, а не учётную запись, из-под которой
    подана заявка. Если почты в реестре нет, создаётся новая запись с указанными
    ФИО, организацией и городом.
    """
    email = str(payload.email).strip().lower()
    participant = db.execute(
        select(models.Participant).where(models.Participant.email == email)
    ).scalar_one_or_none()
    if participant is not None:
        return participant

    participant = models.Participant(
        full_name=payload.full_name.strip(),
        email=email,
        organization=payload.organization,
        city=payload.city,
    )
    db.add(participant)
    db.flush()
    logger.info("Создан участник %s по данным заявки", email)
    return participant


@router.get(
    "",
    response_model=schemas.Page[schemas.ApplicationOut],
    summary="Список заявок",
    description=(
        "Администратор видит все заявки. Участник видит только заявки, поданные из "
        "его учётной записи: выборка фильтруется по владельцу заявки."
    ),
)
def list_applications(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_authenticated),
    conference_id: int | None = Query(None, gt=0),
    section_id: int | None = Query(None, gt=0),
    participant_id: int | None = Query(None, gt=0, description="Только для администратора"),
    app_status: models.ApplicationStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.ApplicationOut]:
    stmt = select(models.Application).order_by(models.Application.created_at.desc())

    if user.is_admin:
        if participant_id is not None:
            stmt = stmt.where(models.Application.participant_id == participant_id)
    else:
        # Участник видит только заявки, поданные из его учётной записи.
        stmt = stmt.where(models.Application.created_by_user_id == user.id)

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
    summary="Создать черновик заявки (только участник)",
    description=(
        "Участник заявки определяется её данными: ФИО и почта обязательны. По почте "
        "находится или создаётся запись реестра участников, поэтому из одной "
        "универсальной учётной записи можно подать заявки на разных людей. Правило "
        "«один человек — одна заявка в секции» сравнивает именно эти данные. "
        "Администратору создание заявок недоступно."
    ),
)
def create_application(
    payload: schemas.ApplicationCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_participant),
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

    participant = _resolve_participant(db, payload)

    duplicate = db.execute(
        select(models.Application).where(
            models.Application.conference_id == payload.conference_id,
            models.Application.section_id == payload.section_id,
            models.Application.participant_id == participant.id,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise conflict(
            "application_duplicate",
            f"У участника «{participant.full_name}» ({participant.email}) уже есть заявка "
            "в этой секции данной конференции",
        )

    application = models.Application(
        conference_id=payload.conference_id,
        section_id=payload.section_id,
        participant_id=participant.id,
        created_by_user_id=user.id,
        topic=payload.topic,
        annotation=payload.annotation,
        format=payload.format,
        needs_hotel=payload.needs_hotel,
    )
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
        details=f"{application.topic} — участник {participant.email}, подал {user.email}",
    )
    db.commit()
    db.refresh(application)
    return application


@router.get(
    "/{application_id}",
    response_model=schemas.ApplicationOut,
    summary="Заявка по id",
    description="Участнику доступна только его собственная заявка, иначе 403.",
)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_authenticated),
) -> models.Application:
    application = _load(db, application_id)
    if not user.is_admin:
        _ensure_owner(user, application)
    return application


@router.patch(
    "/{application_id}",
    response_model=schemas.ApplicationOut,
    summary="Изменить черновик заявки (только участник)",
)
def update_application(
    application_id: int,
    payload: schemas.ApplicationUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_participant),
) -> models.Application:
    application = _load(db, application_id)
    _ensure_owner(user, application)

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
    summary="Удалить черновик заявки (только участник)",
)
def delete_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_participant),
) -> None:
    application = _load(db, application_id)
    _ensure_owner(user, application)

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
    summary="Подать заявку (только участник)",
    description=(
        "Проверяет правила: конференция активна, секция открыта и имеет свободные места. "
        "При нарушении возвращает 409 с кодом правила."
    ),
)
def submit_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_participant),
) -> models.Application:
    application = _load(db, application_id)
    _ensure_owner(user, application)
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
    summary="Принять решение по заявке (только администратор)",
    description=(
        "При принятии заявки автоматически начисляется оргвзнос и приглашение ставится "
        "в очередь рассылки. Решение принимает администратор: свою заявку он подать не "
        "может, поэтому «принять себя» невозможно."
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
    summary="Отозвать заявку (только участник)",
)
def withdraw_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_participant),
) -> models.Application:
    application = _load(db, application_id)
    _ensure_owner(user, application)
    try:
        services.withdraw_application(db, application)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(application)
    return application
