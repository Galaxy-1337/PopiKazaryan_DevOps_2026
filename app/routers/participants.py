"""Маршруты участников конференции.

Доступ: чтение реестра — любой вошедший пользователь (нужно для выбора
участника и просмотра списков), изменение — только организатор.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.routers.deps import conflict, not_found, paginate

router = APIRouter(prefix="/api/v1/participants", tags=["participants"])

require_authenticated = auth.require_authenticated
require_manage = auth.require_permission("participant:manage")


@router.get("", response_model=schemas.Page[schemas.ParticipantOut], summary="Список участников")
def list_participants(
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_authenticated),
    search: str | None = Query(None, min_length=1, max_length=100, description="Поиск по ФИО или e-mail"),
    role: models.ParticipantRole | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.ParticipantOut]:
    stmt = select(models.Participant).order_by(models.Participant.full_name)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            models.Participant.full_name.ilike(pattern) | models.Participant.email.ilike(pattern)
        )
    if role is not None:
        stmt = stmt.where(models.Participant.role == role)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.ParticipantOut)


@router.post(
    "",
    response_model=schemas.ParticipantOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить участника (только организатор)",
)
def create_participant(
    payload: schemas.ParticipantCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_manage),
) -> models.Participant:
    email = str(payload.email).lower()
    duplicate = db.execute(
        select(models.Participant).where(models.Participant.email == email)
    ).scalar_one_or_none()
    if duplicate is not None:
        raise conflict("participant_email_taken", f"Участник с e-mail {email} уже зарегистрирован")

    data = payload.model_dump()
    data["email"] = email
    participant = models.Participant(**data)
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


@router.get("/{participant_id}", response_model=schemas.ParticipantOut, summary="Участник по id")
def get_participant(
    participant_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_authenticated),
) -> models.Participant:
    participant = db.get(models.Participant, participant_id)
    if participant is None:
        raise not_found("Участник", participant_id)
    return participant


@router.patch(
    "/{participant_id}",
    response_model=schemas.ParticipantOut,
    summary="Изменить участника (только организатор)",
)
def update_participant(
    participant_id: int,
    payload: schemas.ParticipantUpdate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_manage),
) -> models.Participant:
    participant = db.get(models.Participant, participant_id)
    if participant is None:
        raise not_found("Участник", participant_id)

    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        email = str(data["email"]).lower()
        duplicate = db.execute(
            select(models.Participant).where(
                models.Participant.email == email, models.Participant.id != participant_id
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise conflict("participant_email_taken", f"Участник с e-mail {email} уже зарегистрирован")
        data["email"] = email

    for field, value in data.items():
        setattr(participant, field, value)

    db.commit()
    db.refresh(participant)
    return participant


@router.delete(
    "/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить участника (только организатор)",
)
def delete_participant(
    participant_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_manage),
) -> None:
    participant = db.get(models.Participant, participant_id)
    if participant is None:
        raise not_found("Участник", participant_id)
    db.delete(participant)
    db.commit()
