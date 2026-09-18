"""Маршруты конференций и секций.

Доступ: чтение — любой вошедший пользователь, изменение — только организатор.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.routers.deps import conflict, not_found, paginate
from app.services import section_load

router = APIRouter(prefix="/api/v1", tags=["conferences"])

# У каждой роли есть хотя бы одно право, поэтому такая зависимость означает
# «пользователь вошёл в систему».
require_authenticated = auth.require_authenticated
require_organizer = auth.require_permission("conference:manage")
require_section_manage = auth.require_permission("section:manage")


# ---------------------------------------------------------------------------
# Конференции
# ---------------------------------------------------------------------------
@router.get(
    "/conferences",
    response_model=schemas.Page[schemas.ConferenceOut],
    summary="Список конференций",
)
def list_conferences(
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_authenticated),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    only_active: bool = Query(False),
) -> schemas.Page[schemas.ConferenceOut]:
    stmt = select(models.Conference).order_by(models.Conference.starts_on.desc())
    if only_active:
        stmt = stmt.where(models.Conference.is_active.is_(True))
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.ConferenceOut)


@router.post(
    "/conferences",
    response_model=schemas.ConferenceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать конференцию (только организатор)",
)
def create_conference(
    payload: schemas.ConferenceCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_organizer),
) -> models.Conference:
    exists = db.execute(
        select(models.Conference).where(models.Conference.slug == payload.slug)
    ).scalar_one_or_none()
    if exists is not None:
        raise conflict("conference_slug_taken", f"Конференция с кодом «{payload.slug}» уже существует")

    conference = models.Conference(**payload.model_dump())
    db.add(conference)
    db.commit()
    db.refresh(conference)
    return conference


@router.get(
    "/conferences/{conference_id}",
    response_model=schemas.ConferenceOut,
    summary="Конференция по id",
)
def get_conference(
    conference_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_authenticated),
) -> models.Conference:
    conference = db.get(models.Conference, conference_id)
    if conference is None:
        raise not_found("Конференция", conference_id)
    return conference


@router.patch(
    "/conferences/{conference_id}",
    response_model=schemas.ConferenceOut,
    summary="Изменить конференцию (только организатор)",
)
def update_conference(
    conference_id: int,
    payload: schemas.ConferenceUpdate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_organizer),
) -> models.Conference:
    conference = db.get(models.Conference, conference_id)
    if conference is None:
        raise not_found("Конференция", conference_id)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(conference, field, value)

    if conference.ends_on < conference.starts_on:
        raise conflict(
            "invalid_conference_dates",
            "Дата окончания не может быть раньше даты начала",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    db.commit()
    db.refresh(conference)
    return conference


@router.delete(
    "/conferences/{conference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить конференцию (только организатор)",
)
def delete_conference(
    conference_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_organizer),
) -> None:
    conference = db.get(models.Conference, conference_id)
    if conference is None:
        raise not_found("Конференция", conference_id)
    db.delete(conference)
    db.commit()


# ---------------------------------------------------------------------------
# Секции
# ---------------------------------------------------------------------------
def _section_out(db: Session, section: models.Section) -> schemas.SectionOut:
    taken = section_load(db, section.id)
    data = schemas.SectionOut.model_validate(section)
    data.taken_seats = taken
    data.free_seats = max(section.capacity - taken, 0)
    return data


@router.get(
    "/sections",
    response_model=schemas.Page[schemas.SectionOut],
    summary="Список секций",
)
def list_sections(
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_authenticated),
    conference_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.SectionOut]:
    stmt = select(models.Section).order_by(models.Section.title)
    if conference_id is not None:
        stmt = stmt.where(models.Section.conference_id == conference_id)
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    return schemas.Page[schemas.SectionOut](
        items=[_section_out(db, row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/sections",
    response_model=schemas.SectionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать секцию (только организатор)",
)
def create_section(
    payload: schemas.SectionCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_section_manage),
) -> schemas.SectionOut:
    conference = db.get(models.Conference, payload.conference_id)
    if conference is None:
        raise not_found("Конференция", payload.conference_id)

    duplicate = db.execute(
        select(models.Section).where(
            models.Section.conference_id == payload.conference_id,
            models.Section.title == payload.title,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise conflict("section_title_taken", "Секция с таким названием уже есть в конференции")

    section = models.Section(**payload.model_dump())
    db.add(section)
    db.commit()
    db.refresh(section)
    return _section_out(db, section)


@router.get(
    "/sections/{section_id}",
    response_model=schemas.SectionOut,
    summary="Секция по id",
)
def get_section(
    section_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_authenticated),
) -> schemas.SectionOut:
    section = db.get(models.Section, section_id)
    if section is None:
        raise not_found("Секция", section_id)
    return _section_out(db, section)


@router.patch(
    "/sections/{section_id}",
    response_model=schemas.SectionOut,
    summary="Изменить секцию (только организатор)",
)
def update_section(
    section_id: int,
    payload: schemas.SectionUpdate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_section_manage),
) -> schemas.SectionOut:
    section = db.get(models.Section, section_id)
    if section is None:
        raise not_found("Секция", section_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(section, field, value)

    taken = section_load(db, section.id)
    if section.capacity < taken:
        raise conflict(
            "section_capacity_below_load",
            f"Нельзя уменьшить вместимость секции ниже числа поданных заявок ({taken})",
        )

    db.commit()
    db.refresh(section)
    return _section_out(db, section)


@router.delete(
    "/sections/{section_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить секцию (только организатор)",
)
def delete_section(
    section_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_section_manage),
) -> None:
    section = db.get(models.Section, section_id)
    if section is None:
        raise not_found("Секция", section_id)
    db.delete(section)
    db.commit()
