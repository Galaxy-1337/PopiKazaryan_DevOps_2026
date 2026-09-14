"""Маршруты приглашений (очередь рассылки), оргвзносов, тезисов и гостиницы."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas, services
from app.database import get_db
from app.routers.deps import conflict, not_found, paginate
from app.services import DomainError

router = APIRouter(prefix="/api/v1", tags=["invitations", "fees", "theses", "hotel"])


# ---------------------------------------------------------------------------
# Приглашения
# ---------------------------------------------------------------------------
@router.get(
    "/invitations",
    response_model=schemas.Page[schemas.InvitationOut],
    tags=["invitations"],
    summary="Очередь рассылки приглашений",
)
def list_invitations(
    db: Session = Depends(get_db),
    inv_status: models.InvitationStatus | None = Query(None, alias="status"),
    participant_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.InvitationOut]:
    stmt = select(models.Invitation).order_by(models.Invitation.queued_at.desc())
    if inv_status is not None:
        stmt = stmt.where(models.Invitation.status == inv_status)
    if participant_id is not None:
        stmt = stmt.where(models.Invitation.participant_id == participant_id)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.InvitationOut)


@router.post(
    "/invitations",
    response_model=schemas.InvitationOut,
    status_code=status.HTTP_201_CREATED,
    tags=["invitations"],
    summary="Поставить приглашение в очередь рассылки",
)
def create_invitation(payload: schemas.InvitationCreate, db: Session = Depends(get_db)) -> models.Invitation:
    application = db.get(models.Application, payload.application_id)
    if application is None:
        raise not_found("Заявка", payload.application_id)

    existing = db.execute(
        select(models.Invitation).where(models.Invitation.application_id == application.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise conflict("invitation_exists", "Приглашение по этой заявке уже создано")

    invitation = services.queue_invitation(db, application)
    db.commit()
    db.refresh(invitation)
    return invitation


@router.post(
    "/invitations/{invitation_id}/send",
    response_model=schemas.InvitationOut,
    tags=["invitations"],
    summary="Отправить приглашение",
)
def send_invitation(
    invitation_id: int,
    success: bool = Query(True, description="Результат отправки (для проверки ветки ошибок)"),
    error: str | None = Query(None, max_length=500),
    db: Session = Depends(get_db),
) -> models.Invitation:
    invitation = db.get(models.Invitation, invitation_id)
    if invitation is None:
        raise not_found("Приглашение", invitation_id)
    try:
        services.send_invitation(db, invitation, success=success, error=error)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(invitation)
    return invitation


# ---------------------------------------------------------------------------
# Оргвзносы
# ---------------------------------------------------------------------------
@router.get(
    "/fees",
    response_model=schemas.Page[schemas.FeeOut],
    tags=["fees"],
    summary="Список оргвзносов",
)
def list_fees(
    db: Session = Depends(get_db),
    fee_status: models.FeeStatus | None = Query(None, alias="status"),
    application_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.FeeOut]:
    stmt = select(models.Fee).order_by(models.Fee.created_at.desc())
    if fee_status is not None:
        stmt = stmt.where(models.Fee.status == fee_status)
    if application_id is not None:
        stmt = stmt.where(models.Fee.application_id == application_id)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.FeeOut)


@router.post(
    "/fees",
    response_model=schemas.FeeOut,
    status_code=status.HTTP_201_CREATED,
    tags=["fees"],
    summary="Начислить оргвзнос",
)
def create_fee(payload: schemas.FeeCreate, db: Session = Depends(get_db)) -> models.Fee:
    application = db.get(models.Application, payload.application_id)
    if application is None:
        raise not_found("Заявка", payload.application_id)
    if application.status != models.ApplicationStatus.ACCEPTED:
        raise conflict(
            "fee_requires_accepted_application",
            "Оргвзнос начисляется только по принятой заявке",
        )

    fee = services.charge_fee(db, application)
    if payload.amount is not None:
        fee.amount = payload.amount
    if payload.comment:
        fee.comment = payload.comment
    db.commit()
    db.refresh(fee)
    return fee


@router.post("/fees/{fee_id}/pay", response_model=schemas.FeeOut, tags=["fees"], summary="Оплатить оргвзнос")
def pay_fee(fee_id: int, payload: schemas.FeePayment, db: Session = Depends(get_db)) -> models.Fee:
    fee = db.execute(
        select(models.Fee).options(selectinload(models.Fee.application)).where(models.Fee.id == fee_id)
    ).scalar_one_or_none()
    if fee is None:
        raise not_found("Оргвзнос", fee_id)
    try:
        services.pay_fee(db, fee, payment_reference=payload.payment_reference)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(fee)
    return fee


@router.post(
    "/fees/{fee_id}/refund", response_model=schemas.FeeOut, tags=["fees"], summary="Вернуть оргвзнос"
)
def refund_fee(fee_id: int, payload: schemas.FeeRefund, db: Session = Depends(get_db)) -> models.Fee:
    fee = db.execute(
        select(models.Fee).options(selectinload(models.Fee.application)).where(models.Fee.id == fee_id)
    ).scalar_one_or_none()
    if fee is None:
        raise not_found("Оргвзнос", fee_id)
    try:
        services.refund_fee(db, fee, reason=payload.reason)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(fee)
    return fee


# ---------------------------------------------------------------------------
# Тезисы
# ---------------------------------------------------------------------------
@router.get(
    "/theses", response_model=schemas.Page[schemas.ThesisOut], tags=["theses"], summary="Список тезисов"
)
def list_theses(
    db: Session = Depends(get_db),
    thesis_status: models.ThesisStatus | None = Query(None, alias="status"),
    application_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.ThesisOut]:
    stmt = select(models.Thesis).order_by(models.Thesis.created_at.desc())
    if thesis_status is not None:
        stmt = stmt.where(models.Thesis.status == thesis_status)
    if application_id is not None:
        stmt = stmt.where(models.Thesis.application_id == application_id)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.ThesisOut)


@router.post(
    "/applications/{application_id}/theses",
    response_model=schemas.ThesisOut,
    status_code=status.HTTP_201_CREATED,
    tags=["theses"],
    summary="Добавить тезисы к заявке",
)
def create_thesis(
    application_id: int, payload: schemas.ThesisCreate, db: Session = Depends(get_db)
) -> models.Thesis:
    application = db.execute(
        select(models.Application)
        .options(selectinload(models.Application.theses))
        .where(models.Application.id == application_id)
    ).scalar_one_or_none()
    if application is None:
        raise not_found("Заявка", application_id)

    thesis = models.Thesis(**payload.model_dump())
    try:
        services.add_thesis(db, application, thesis)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(thesis)
    return thesis


@router.get("/theses/{thesis_id}", response_model=schemas.ThesisOut, tags=["theses"], summary="Тезисы по id")
def get_thesis(thesis_id: int, db: Session = Depends(get_db)) -> models.Thesis:
    thesis = db.get(models.Thesis, thesis_id)
    if thesis is None:
        raise not_found("Тезисы", thesis_id)
    return thesis


@router.post(
    "/theses/{thesis_id}/review",
    response_model=schemas.ThesisOut,
    tags=["theses"],
    summary="Зафиксировать рецензию",
    description="Порог принятия — 6 баллов из 10 (правило предметной области).",
)
def review_thesis(
    thesis_id: int, payload: schemas.ThesisReview, db: Session = Depends(get_db)
) -> models.Thesis:
    thesis = db.get(models.Thesis, thesis_id)
    if thesis is None:
        raise not_found("Тезисы", thesis_id)
    try:
        services.review_thesis(
            db,
            thesis,
            reviewer_name=payload.reviewer_name,
            score=payload.score,
            accepted=payload.accepted,
            comment=payload.comment,
        )
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(thesis)
    return thesis


# ---------------------------------------------------------------------------
# Гостиница
# ---------------------------------------------------------------------------
@router.get(
    "/hotel-bookings",
    response_model=schemas.Page[schemas.HotelBookingOut],
    tags=["hotel"],
    summary="Потребность в гостинице",
)
def list_hotel_bookings(
    db: Session = Depends(get_db),
    hotel_status: models.HotelStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.HotelBookingOut]:
    stmt = select(models.HotelBooking).order_by(models.HotelBooking.check_in)
    if hotel_status is not None:
        stmt = stmt.where(models.HotelBooking.status == hotel_status)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.HotelBookingOut)


@router.post(
    "/hotel-bookings",
    response_model=schemas.HotelBookingOut,
    status_code=status.HTTP_201_CREATED,
    tags=["hotel"],
    summary="Создать потребность в гостинице",
    description=(
        "Правила: заявка должна быть принята, формат участия — не дистанционный, "
        "даты проживания — в пределах дат конференции."
    ),
)
def create_hotel_booking(
    payload: schemas.HotelBookingCreate, db: Session = Depends(get_db)
) -> models.HotelBooking:
    application = db.execute(
        select(models.Application)
        .options(
            selectinload(models.Application.conference),
            selectinload(models.Application.hotel_booking),
        )
        .where(models.Application.id == payload.application_id)
    ).scalar_one_or_none()
    if application is None:
        raise not_found("Заявка", payload.application_id)

    data = payload.model_dump(exclude={"application_id"})
    try:
        booking = services.create_hotel_booking(db, application, **data)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(booking)
    return booking


@router.get(
    "/hotel-bookings/{booking_id}",
    response_model=schemas.HotelBookingOut,
    tags=["hotel"],
    summary="Бронь по id",
)
def get_hotel_booking(booking_id: int, db: Session = Depends(get_db)) -> models.HotelBooking:
    booking = db.get(models.HotelBooking, booking_id)
    if booking is None:
        raise not_found("Бронь гостиницы", booking_id)
    return booking


@router.post(
    "/hotel-bookings/{booking_id}/confirm",
    response_model=schemas.HotelBookingOut,
    tags=["hotel"],
    summary="Подтвердить бронь",
    description="Бронь, не подтверждённая в установленный срок, не может быть подтверждена.",
)
def confirm_hotel_booking(booking_id: int, db: Session = Depends(get_db)) -> models.HotelBooking:
    booking = db.get(models.HotelBooking, booking_id)
    if booking is None:
        raise not_found("Бронь гостиницы", booking_id)
    try:
        services.confirm_hotel_booking(db, booking)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(booking)
    return booking


@router.post(
    "/hotel-bookings/expire-stale",
    tags=["hotel"],
    summary="Пометить просроченные брони",
    description="Служебная операция: переводит брони с истёкшим сроком в статус expired.",
)
def expire_stale_bookings(db: Session = Depends(get_db)) -> dict[str, int]:
    expired = services.expire_stale_hotel_bookings(db)
    db.commit()
    return {"expired": expired}
