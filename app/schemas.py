"""Pydantic-схемы: валидация входных данных и формат ответов API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import (
    ApplicationStatus,
    FeeStatus,
    HotelStatus,
    InvitationStatus,
    ParticipantRole,
    ParticipationFormat,
    ThesisStatus,
)

T = TypeVar("T")

ORM = ConfigDict(from_attributes=True)

NonEmptyStr = Annotated[str, Field(min_length=1, max_length=300)]


class ErrorBody(BaseModel):
    """Тело ошибки — единый формат для всех ответов с кодом >= 400."""

    code: str = Field(description="Машиночитаемый код ошибки")
    message: str = Field(description="Пояснение для человека")
    details: list[dict] | None = Field(default=None, description="Детали валидации")


class ErrorResponse(BaseModel):
    error: ErrorBody


class Page(BaseModel, Generic[T]):
    """Страница результатов с метаданными пагинации."""

    items: list[T]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Конференции и секции
# ---------------------------------------------------------------------------
class ConferenceCreate(BaseModel):
    title: NonEmptyStr
    slug: Annotated[str, Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9\-]*$")]
    description: str | None = None
    starts_on: date
    ends_on: date
    location: Annotated[str, Field(min_length=1, max_length=200)] = "Москва"
    fee_amount: Annotated[Decimal, Field(ge=0)] = Decimal("0.00")
    is_active: bool = True

    @field_validator("ends_on")
    @classmethod
    def _check_dates(cls, value: date, info) -> date:  # noqa: ANN001
        starts_on = info.data.get("starts_on")
        if starts_on is not None and value < starts_on:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        return value


class ConferenceUpdate(BaseModel):
    title: NonEmptyStr | None = None
    description: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    location: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    fee_amount: Annotated[Decimal, Field(ge=0)] | None = None
    is_active: bool | None = None


class ConferenceOut(BaseModel):
    model_config = ORM

    id: int
    title: str
    slug: str
    description: str | None
    starts_on: date
    ends_on: date
    location: str
    fee_amount: Decimal
    is_active: bool


class SectionCreate(BaseModel):
    conference_id: int = Field(gt=0)
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None
    capacity: Annotated[int, Field(gt=0, le=1000)] = 3
    is_open: bool = True


class SectionUpdate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: str | None = None
    capacity: Annotated[int, Field(gt=0, le=1000)] | None = None
    is_open: bool | None = None


class SectionOut(BaseModel):
    model_config = ORM

    id: int
    conference_id: int
    title: str
    description: str | None
    capacity: int
    is_open: bool
    taken_seats: int = 0
    free_seats: int = 0


# ---------------------------------------------------------------------------
# Участники
# ---------------------------------------------------------------------------
class ParticipantCreate(BaseModel):
    full_name: Annotated[str, Field(min_length=3, max_length=200)]
    email: EmailStr
    phone: Annotated[str, Field(max_length=30)] | None = None
    organization: Annotated[str, Field(max_length=250)] | None = None
    position: Annotated[str, Field(max_length=150)] | None = None
    academic_degree: Annotated[str, Field(max_length=120)] | None = None
    city: Annotated[str, Field(max_length=120)] | None = None
    role: ParticipantRole = ParticipantRole.LISTENER
    is_active: bool = True


class ParticipantUpdate(BaseModel):
    full_name: Annotated[str, Field(min_length=3, max_length=200)] | None = None
    email: EmailStr | None = None
    phone: Annotated[str, Field(max_length=30)] | None = None
    organization: Annotated[str, Field(max_length=250)] | None = None
    position: Annotated[str, Field(max_length=150)] | None = None
    academic_degree: Annotated[str, Field(max_length=120)] | None = None
    city: Annotated[str, Field(max_length=120)] | None = None
    role: ParticipantRole | None = None
    is_active: bool | None = None


class ParticipantOut(BaseModel):
    """Формат ответа по участнику.

    Поле ``email`` намеренно объявлено как обычная строка, а не ``EmailStr``:
    строгая проверка нужна при приёме данных (см. ``ParticipantCreate``), а на
    выдаче она привела бы к ошибке 500, если в базе окажется адрес из служебной
    зоны (например, ``.local``), который сам API никогда не принял бы.
    """

    model_config = ORM

    id: int
    full_name: str
    email: str
    phone: str | None
    organization: str | None
    position: str | None
    academic_degree: str | None
    city: str | None
    role: ParticipantRole
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------------------
class ApplicationCreate(BaseModel):
    conference_id: int = Field(gt=0)
    section_id: int = Field(gt=0)
    participant_id: int = Field(gt=0)
    topic: Annotated[str, Field(min_length=3, max_length=300)]
    annotation: str | None = None
    format: ParticipationFormat = ParticipationFormat.OFFLINE
    needs_hotel: bool = False


class ApplicationUpdate(BaseModel):
    topic: Annotated[str, Field(min_length=3, max_length=300)] | None = None
    annotation: str | None = None
    format: ParticipationFormat | None = None
    needs_hotel: bool | None = None
    section_id: int | None = Field(default=None, gt=0)


class ApplicationDecision(BaseModel):
    accept: bool
    comment: Annotated[str, Field(max_length=2000)] | None = None


class ApplicationOut(BaseModel):
    model_config = ORM

    id: int
    conference_id: int
    section_id: int
    participant_id: int
    topic: str
    annotation: str | None
    format: ParticipationFormat
    status: ApplicationStatus
    needs_hotel: bool
    submitted_at: datetime | None
    decided_at: datetime | None
    decision_comment: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Приглашения
# ---------------------------------------------------------------------------
class InvitationCreate(BaseModel):
    application_id: int = Field(gt=0)


class InvitationOut(BaseModel):
    model_config = ORM

    id: int
    application_id: int
    participant_id: int
    subject: str
    body: str
    status: InvitationStatus
    attempts: int
    last_error: str | None
    queued_at: datetime
    sent_at: datetime | None


# ---------------------------------------------------------------------------
# Оргвзносы
# ---------------------------------------------------------------------------
class FeeCreate(BaseModel):
    application_id: int = Field(gt=0)
    amount: Annotated[Decimal, Field(ge=0)] | None = None
    comment: Annotated[str, Field(max_length=1000)] | None = None


class FeePayment(BaseModel):
    payment_reference: Annotated[str, Field(min_length=3, max_length=100)] | None = None


class FeeRefund(BaseModel):
    reason: Annotated[str, Field(min_length=3, max_length=1000)]


class FeeOut(BaseModel):
    model_config = ORM

    id: int
    application_id: int
    amount: Decimal
    currency: str
    status: FeeStatus
    payment_reference: str | None
    paid_at: datetime | None
    refunded_at: datetime | None
    comment: str | None


# ---------------------------------------------------------------------------
# Тезисы
# ---------------------------------------------------------------------------
class ThesisCreate(BaseModel):
    title: Annotated[str, Field(min_length=3, max_length=300)]
    abstract: Annotated[str, Field(min_length=50)]
    keywords: Annotated[str, Field(max_length=400)] | None = None
    file_name: Annotated[str, Field(max_length=255)] | None = None
    file_size_kb: Annotated[int, Field(ge=0)] | None = None


class ThesisReview(BaseModel):
    reviewer_name: Annotated[str, Field(min_length=3, max_length=200)]
    score: Annotated[int, Field(ge=1, le=10)]
    accepted: bool = True
    comment: Annotated[str, Field(max_length=2000)] | None = None


class ThesisOut(BaseModel):
    model_config = ORM

    id: int
    application_id: int
    title: str
    abstract: str
    keywords: str | None
    file_name: str | None
    file_size_kb: int | None
    status: ThesisStatus
    reviewer_name: str | None
    review_score: int | None
    review_comment: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None


# ---------------------------------------------------------------------------
# Гостиница
# ---------------------------------------------------------------------------
class HotelBookingCreate(BaseModel):
    application_id: int = Field(gt=0)
    hotel_name: Annotated[str, Field(min_length=2, max_length=200)]
    room_type: Annotated[str, Field(max_length=80)] = "standard"
    guests_count: Annotated[int, Field(gt=0, le=10)] = 1
    check_in: date
    check_out: date

    @field_validator("check_out")
    @classmethod
    def _check_dates(cls, value: date, info) -> date:  # noqa: ANN001
        check_in = info.data.get("check_in")
        if check_in is not None and value <= check_in:
            raise ValueError("Дата выезда должна быть позже даты заезда")
        return value


class HotelBookingOut(BaseModel):
    model_config = ORM

    id: int
    application_id: int
    hotel_name: str
    room_type: str
    guests_count: int
    check_in: date
    check_out: date
    nights: int
    status: HotelStatus
    confirmation_deadline: datetime
    confirmed_at: datetime | None
    comment: str | None


# ---------------------------------------------------------------------------
# Служебные ответы
# ---------------------------------------------------------------------------
class HealthOut(BaseModel):
    status: str = Field(description="ok | degraded")
    version: str
    database: str
    app_env: str
    checked_at: datetime


# ---------------------------------------------------------------------------
# Аутентификация и роли
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    """Данные для входа в систему."""

    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=200)]


class CurrentUserOut(BaseModel):
    """Сведения о текущем пользователе для интерфейса."""

    model_config = ORM

    id: int
    email: str
    full_name: str
    role: ParticipantRole
    role_title: str
    participant_id: int | None
    is_active: bool
    last_login_at: datetime | None


class RoleOut(BaseModel):
    """Роль и перечень доступных ей действий."""

    role: ParticipantRole
    title: str
    permissions: list[str]


class ReportOut(BaseModel):
    """Сводный отчёт для очередей рассылки и планирования гостиницы."""

    conference_id: int
    conference_title: str
    applications_total: int
    applications_by_status: dict[str, int]
    participants_total: int
    fees_total_amount: Decimal
    fees_paid_amount: Decimal
    fees_by_status: dict[str, int]
    theses_total: int
    theses_by_status: dict[str, int]
    invitations_by_status: dict[str, int]
    hotel_bookings_total: int
    hotel_guests_total: int
    hotel_by_status: dict[str, int]
    generated_at: datetime


__all__ = [
    "ApplicationCreate",
    "ApplicationDecision",
    "ApplicationOut",
    "ApplicationUpdate",
    "ConferenceCreate",
    "ConferenceOut",
    "ConferenceUpdate",
    "CurrentUserOut",
    "ErrorBody",
    "ErrorResponse",
    "FeeCreate",
    "FeeOut",
    "FeePayment",
    "FeeRefund",
    "HealthOut",
    "HotelBookingCreate",
    "HotelBookingOut",
    "InvitationCreate",
    "InvitationOut",
    "LoginRequest",
    "Page",
    "ParticipantCreate",
    "ParticipantOut",
    "ParticipantUpdate",
    "ReportOut",
    "RoleOut",
    "SectionCreate",
    "SectionOut",
    "SectionUpdate",
    "ThesisCreate",
    "ThesisOut",
    "ThesisReview",
]
