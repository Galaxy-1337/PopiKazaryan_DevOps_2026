"""Маршруты приглашений, оргвзносов, тезисов и гостиницы.

Разграничение доступа:

* приглашения — организатор управляет рассылкой, участник видит только свои;
* оргвзносы — организатор начисляет и возвращает, участник и докладчик видят
  и оплачивают только свои;
* тезисы — докладчик подаёт их по своей заявке, рецензент выставляет оценку,
  организатор видит все;
* гостиница — участник и докладчик оформляют потребность по своим заявкам,
  организатор управляет всеми бронями.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import auth, models, schemas, services
from app.database import get_db
from app.routers.deps import conflict, not_found, paginate
from app.services import DomainError

router = APIRouter(prefix="/api/v1", tags=["invitations", "fees", "theses", "hotel"])

require_authenticated = auth.require_authenticated
require_invitation_manage = auth.require_permission("invitation:manage")
require_fee_manage = auth.require_permission("fee:manage")
require_own_fee = auth.require_any_permission("fee:read_own", "fee:pay_own")
require_thesis_submit = auth.require_permission("thesis:submit_own")
require_thesis_review = auth.require_permission("thesis:review")
require_thesis_read = auth.require_any_permission("thesis:read_all", "thesis:read_own", "thesis:submit_own")
require_hotel_manage = auth.require_permission("hotel:manage")
require_own_hotel = auth.require_any_permission("hotel:request_own", "fee:read_own")


def _application_for_user(db: Session, application_id: int) -> models.Application:
    application = db.execute(
        select(models.Application)
        .options(
            selectinload(models.Application.conference),
            selectinload(models.Application.hotel_booking),
        )
        .where(models.Application.id == application_id)
    ).scalar_one_or_none()
    if application is None:
        raise not_found("Заявка", application_id)
    return application


def _ensure_owner_or_organizer(user: models.User, application: models.Application, what: str) -> None:
    """Проверить, что пользователь — владелец заявки либо организатор."""
    if auth.has_permission(user, "application:decide"):
        return
    if user.participant_id != application.participant_id:
        raise conflict(
            "forbidden_not_owner",
            f"{what}: доступно только автору заявки или организатору",
            http_status=status.HTTP_403_FORBIDDEN,
        )


# ---------------------------------------------------------------------------
# Приглашения
# ---------------------------------------------------------------------------
@router.get(
    "/invitations",
    response_model=schemas.Page[schemas.InvitationOut],
    tags=["invitations"],
    summary="Очередь рассылки приглашений",
    description=(
        "Организатор видит всю очередь рассылки. Участник, докладчик и рецензент "
        "видят только приглашения, адресованные им."
    ),
)
def list_invitations(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_authenticated),
    inv_status: models.InvitationStatus | None = Query(None, alias="status"),
    participant_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.InvitationOut]:
    stmt = select(models.Invitation).order_by(models.Invitation.queued_at.desc())

    if auth.has_permission(user, "invitation:manage"):
        if participant_id is not None:
            stmt = stmt.where(models.Invitation.participant_id == participant_id)
    else:
        if user.participant_id is None:
            return schemas.Page[schemas.InvitationOut](items=[], total=0, limit=limit, offset=offset)
        stmt = stmt.where(models.Invitation.participant_id == user.participant_id)

    if inv_status is not None:
        stmt = stmt.where(models.Invitation.status == inv_status)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.InvitationOut)


@router.post(
    "/invitations",
    response_model=schemas.InvitationOut,
    status_code=status.HTTP_201_CREATED,
    tags=["invitations"],
    summary="Поставить приглашение в очередь рассылки (только организатор)",
)
def create_invitation(
    payload: schemas.InvitationCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_invitation_manage),
) -> models.Invitation:
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
    summary="Отправить приглашение (только организатор)",
)
def send_invitation(
    invitation_id: int,
    success: bool = Query(True, description="Результат отправки (для проверки ветки ошибок)"),
    error: str | None = Query(None, max_length=500),
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_invitation_manage),
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
    description=(
        "Организатор видит все начисления. Участник и докладчик видят только взносы по своим заявкам."
    ),
)
def list_fees(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_authenticated),
    fee_status: models.FeeStatus | None = Query(None, alias="status"),
    application_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.FeeOut]:
    stmt = select(models.Fee).order_by(models.Fee.created_at.desc())

    if not auth.has_permission(user, "fee:manage"):
        if user.participant_id is None:
            return schemas.Page[schemas.FeeOut](items=[], total=0, limit=limit, offset=offset)
        own_applications = select(models.Application.id).where(
            models.Application.participant_id == user.participant_id
        )
        stmt = stmt.where(models.Fee.application_id.in_(own_applications))

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
    summary="Начислить оргвзнос (только организатор)",
)
def create_fee(
    payload: schemas.FeeCreate,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_fee_manage),
) -> models.Fee:
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


@router.post(
    "/fees/{fee_id}/pay",
    response_model=schemas.FeeOut,
    tags=["fees"],
    summary="Оплатить оргвзнос",
    description=(
        "Участник и докладчик оплачивают только взносы по своим заявкам. "
        "Организатор может отметить оплату любого взноса."
    ),
)
def pay_fee(
    fee_id: int,
    payload: schemas.FeePayment,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_own_fee),
) -> models.Fee:
    fee = db.execute(
        select(models.Fee)
        .options(selectinload(models.Fee.application).selectinload(models.Application.participant))
        .where(models.Fee.id == fee_id)
    ).scalar_one_or_none()
    if fee is None:
        raise not_found("Оргвзнос", fee_id)

    if not auth.has_permission(user, "fee:manage") and (
        user.participant_id != fee.application.participant_id
    ):
        raise conflict(
            "forbidden_foreign_fee",
            "Оплатить можно только оргвзнос по своей заявке",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    try:
        services.pay_fee(db, fee, payment_reference=payload.payment_reference)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(fee)
    return fee


@router.post(
    "/fees/{fee_id}/refund",
    response_model=schemas.FeeOut,
    tags=["fees"],
    summary="Вернуть оргвзнос (только организатор)",
)
def refund_fee(
    fee_id: int,
    payload: schemas.FeeRefund,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_fee_manage),
) -> models.Fee:
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
    "/theses",
    response_model=schemas.Page[schemas.ThesisOut],
    tags=["theses"],
    summary="Список тезисов",
    description=(
        "Рецензент и организатор видят все тезисы. Докладчик видит только свои, "
        "участник-слушатель тезисов не подаёт."
    ),
)
def list_theses(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_thesis_read),
    thesis_status: models.ThesisStatus | None = Query(None, alias="status"),
    application_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.ThesisOut]:
    stmt = select(models.Thesis).order_by(models.Thesis.created_at.desc())

    if not auth.has_permission(user, "thesis:read_all"):
        if user.participant_id is None:
            return schemas.Page[schemas.ThesisOut](items=[], total=0, limit=limit, offset=offset)
        own_applications = select(models.Application.id).where(
            models.Application.participant_id == user.participant_id
        )
        stmt = stmt.where(models.Thesis.application_id.in_(own_applications))

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
    description="Докладчик подаёт тезисы по своей заявке (организатор — по любой).",
)
def create_thesis(
    application_id: int,
    payload: schemas.ThesisCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_thesis_submit),
) -> models.Thesis:
    application = db.execute(
        select(models.Application)
        .options(selectinload(models.Application.theses))
        .where(models.Application.id == application_id)
    ).scalar_one_or_none()
    if application is None:
        raise not_found("Заявка", application_id)

    _ensure_owner_or_organizer(user, application, "Подача тезисов")

    thesis = models.Thesis(**payload.model_dump())
    try:
        services.add_thesis(db, application, thesis)
    except DomainError as exc:
        raise conflict(exc.code, exc.message, http_status=exc.status_code) from exc
    db.commit()
    db.refresh(thesis)
    return thesis


@router.get(
    "/theses/{thesis_id}",
    response_model=schemas.ThesisOut,
    tags=["theses"],
    summary="Тезисы по id",
)
def get_thesis(
    thesis_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_thesis_read),
) -> models.Thesis:
    thesis = db.execute(
        select(models.Thesis)
        .options(selectinload(models.Thesis.application))
        .where(models.Thesis.id == thesis_id)
    ).scalar_one_or_none()
    if thesis is None:
        raise not_found("Тезисы", thesis_id)

    if not auth.has_permission(user, "thesis:read_all") and (
        user.participant_id != thesis.application.participant_id
    ):
        raise conflict(
            "forbidden_foreign_thesis",
            "Тезисы принадлежат другому участнику",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    return thesis


@router.post(
    "/theses/{thesis_id}/review",
    response_model=schemas.ThesisOut,
    tags=["theses"],
    summary="Зафиксировать рецензию (только рецензент)",
    description="Порог принятия — 6 баллов из 10 (правило предметной области).",
)
def review_thesis(
    thesis_id: int,
    payload: schemas.ThesisReview,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_thesis_review),
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
    description=("Организатор видит все брони. Участник и докладчик видят брони по своим заявкам."),
)
def list_hotel_bookings(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_authenticated),
    hotel_status: models.HotelStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.HotelBookingOut]:
    stmt = select(models.HotelBooking).order_by(models.HotelBooking.check_in)

    if not auth.has_permission(user, "hotel:manage"):
        if user.participant_id is None:
            return schemas.Page[schemas.HotelBookingOut](items=[], total=0, limit=limit, offset=offset)
        own_applications = select(models.Application.id).where(
            models.Application.participant_id == user.participant_id
        )
        stmt = stmt.where(models.HotelBooking.application_id.in_(own_applications))

    if hotel_status is not None:
        stmt = stmt.where(models.HotelBooking.status == hotel_status)
    return paginate(db, stmt, limit=limit, offset=offset, schema=schemas.HotelBookingOut)


@router.post(
    "/hotel-bookings",
    response_model=schemas.HotelBookingOut,
    status_code=status.HTTP_201_CREATED,
    tags=["hotel"],
    summary="Оформить потребность в гостинице",
    description=(
        "Правила: заявка должна быть принята, формат участия — не дистанционный, "
        "даты проживания — в пределах дат конференции. Участник оформляет бронь по "
        "своей заявке, организатор — по любой."
    ),
)
def create_hotel_booking(
    payload: schemas.HotelBookingCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_own_hotel),
) -> models.HotelBooking:
    application = _application_for_user(db, payload.application_id)
    _ensure_owner_or_organizer(user, application, "Оформление гостиницы")

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
def get_hotel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_authenticated),
) -> models.HotelBooking:
    booking = db.execute(
        select(models.HotelBooking)
        .options(selectinload(models.HotelBooking.application))
        .where(models.HotelBooking.id == booking_id)
    ).scalar_one_or_none()
    if booking is None:
        raise not_found("Бронь гостиницы", booking_id)

    if not auth.has_permission(user, "hotel:manage") and (
        user.participant_id != booking.application.participant_id
    ):
        raise conflict(
            "forbidden_foreign_booking",
            "Бронь относится к заявке другого участника",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    return booking


@router.post(
    "/hotel-bookings/{booking_id}/confirm",
    response_model=schemas.HotelBookingOut,
    tags=["hotel"],
    summary="Подтвердить бронь (только организатор)",
    description="Бронь, не подтверждённая в установленный срок, не может быть подтверждена.",
)
def confirm_hotel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_hotel_manage),
) -> models.HotelBooking:
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
    summary="Пометить просроченные брони (только организатор)",
    description="Служебная операция: переводит брони с истёкшим сроком в статус expired.",
)
def expire_stale_bookings(
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_hotel_manage),
) -> dict[str, int]:
    expired = services.expire_stale_hotel_bookings(db)
    db.commit()
    return {"expired": expired}
