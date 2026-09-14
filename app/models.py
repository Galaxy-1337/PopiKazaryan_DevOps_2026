"""Модели предметной области «Конференция».

Сущности и связи
----------------
* ``Conference`` — мероприятие (конференция), задаёт даты, размер оргвзноса и
  правила приёма заявок.
* ``Section`` — секция конференции (тематическое направление) с ограничением по
  числу участников.
* ``Participant`` — участник: ФИО, организация, контактные данные, роль.
* ``Application`` — заявка участника на участие в секции (центральная сущность
  жизненного цикла: черновик → подана → принята/отклонена → отозвана).
* ``Invitation`` — приглашение, поставленное в очередь рассылки и отправленное
  участнику.
* ``Fee`` — оргвзнос по заявке (начисление, оплата, возврат).
* ``Thesis`` — тезисы доклада, привязанные к заявке, с результатом рецензии.
* ``HotelBooking`` — потребность в гостинице по заявке с ограниченным сроком
  подтверждения брони.

Связи реализованы через внешние ключи с каскадным удалением дочерних записей,
уникальные ограничения защищают бизнес-правила на уровне СУБД.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    """Текущее время в UTC (timezone-aware)."""
    return datetime.now(UTC)


def as_aware(value: datetime) -> datetime:
    """Привести время к timezone-aware виду.

    SQLite не хранит информацию о часовом поясе и возвращает «наивные» значения
    (это известное ограничение драйвера), поэтому перед сравнением с ``utcnow()``
    такие значения помечаются как UTC. PostgreSQL возвращает aware-значения,
    и функция ничего не меняет.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class ApplicationStatus(enum.StrEnum):
    """Статусы заявки — основа жизненного цикла участия."""

    DRAFT = "draft"  # черновик, ещё не отправлена
    SUBMITTED = "submitted"  # подана, ожидает решения программного комитета
    ACCEPTED = "accepted"  # принята (заявка одобрена)
    REJECTED = "rejected"  # отклонена
    WITHDRAWN = "withdrawn"  # отозвана участником


class ParticipationFormat(enum.StrEnum):
    """Формат участия."""

    OFFLINE = "offline"  # очное
    ONLINE = "online"  # дистанционное
    POSTER = "poster"  # стендовый доклад


class ParticipantRole(enum.StrEnum):
    """Роль участника в конференции."""

    LISTENER = "listener"  # слушатель
    SPEAKER = "speaker"  # докладчик
    ORGANIZER = "organizer"  # организатор
    REVIEWER = "reviewer"  # рецензент


class FeeStatus(enum.StrEnum):
    """Статусы оргвзноса."""

    PENDING = "pending"  # начислен, ожидает оплаты
    PAID = "paid"  # оплачен
    REFUNDED = "refunded"  # возвращён
    CANCELLED = "cancelled"  # отменён


class ThesisStatus(enum.StrEnum):
    """Статусы тезисов."""

    DRAFT = "draft"  # черновик
    SUBMITTED = "submitted"  # отправлены на рецензию
    UNDER_REVIEW = "under_review"  # на рецензии
    ACCEPTED = "accepted"  # приняты к публикации
    REVISION = "revision"  # требуют доработки
    REJECTED = "rejected"  # отклонены


class InvitationStatus(enum.StrEnum):
    """Статусы приглашения (очередь рассылки)."""

    QUEUED = "queued"  # в очереди на отправку
    SENT = "sent"  # отправлено
    DELIVERED = "delivered"  # доставлено
    FAILED = "failed"  # ошибка отправки
    CANCELLED = "cancelled"  # отменено


class HotelStatus(enum.StrEnum):
    """Статусы брони гостиницы."""

    REQUESTED = "requested"  # запрошена, ожидает подтверждения
    CONFIRMED = "confirmed"  # подтверждена
    CHECKED_IN = "checked_in"  # участник заселён
    CANCELLED = "cancelled"  # отменена
    EXPIRED = "expired"  # истёк срок подтверждения


class Conference(Base):
    """Конференция (мероприятие)."""

    __tablename__ = "conferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False, default="Москва")
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    sections: Mapped[list[Section]] = relationship(
        back_populates="conference", cascade="all, delete-orphan", order_by="Section.title"
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="conference", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("ends_on >= starts_on", name="ck_conference_dates"),
        CheckConstraint("fee_amount >= 0", name="ck_conference_fee_non_negative"),
    )

    @property
    def duration_days(self) -> int:
        return (self.ends_on - self.starts_on).days + 1

    def __repr__(self) -> str:  # pragma: no cover - отладочный вывод
        return f"<Conference id={self.id} slug={self.slug!r}>"


class Section(Base):
    """Секция конференции (тематическое направление)."""

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conference_id: Mapped[int] = mapped_column(
        ForeignKey("conferences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    conference: Mapped[Conference] = relationship(back_populates="sections")
    applications: Mapped[list[Application]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("conference_id", "title", name="uq_section_title_per_conference"),
        CheckConstraint("capacity > 0", name="ck_section_capacity_positive"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Section id={self.id} title={self.title!r}>"


class Participant(Base):
    """Участник конференции."""

    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    organization: Mapped[str | None] = mapped_column(String(250))
    position: Mapped[str | None] = mapped_column(String(150))
    academic_degree: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[ParticipantRole] = mapped_column(
        Enum(ParticipantRole, native_enum=False, length=20),
        nullable=False,
        default=ParticipantRole.LISTENER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    applications: Mapped[list[Application]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )
    invitations: Mapped[list[Invitation]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )

    @property
    def short_name(self) -> str:
        """Фамилия и инициалы: «Иванов И. И.»."""
        parts = self.full_name.split()
        if len(parts) < 2:
            return self.full_name
        initials = " ".join(f"{p[0]}." for p in parts[1:3])
        return f"{parts[0]} {initials}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Participant id={self.id} email={self.email!r}>"


class Application(Base):
    """Заявка участника на участие в секции конференции."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conference_id: Mapped[int] = mapped_column(
        ForeignKey("conferences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    annotation: Mapped[str | None] = mapped_column(Text)
    format: Mapped[ParticipationFormat] = mapped_column(
        Enum(ParticipationFormat, native_enum=False, length=20),
        nullable=False,
        default=ParticipationFormat.OFFLINE,
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=20),
        nullable=False,
        default=ApplicationStatus.DRAFT,
        index=True,
    )
    needs_hotel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    conference: Mapped[Conference] = relationship(back_populates="applications")
    section: Mapped[Section] = relationship(back_populates="applications")
    participant: Mapped[Participant] = relationship(back_populates="applications")
    invitation: Mapped[Invitation | None] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )
    fees: Mapped[list[Fee]] = relationship(back_populates="application", cascade="all, delete-orphan")
    theses: Mapped[list[Thesis]] = relationship(back_populates="application", cascade="all, delete-orphan")
    hotel_booking: Mapped[HotelBooking | None] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        # Один участник — одна заявка в конкретной секции конкретной конференции.
        UniqueConstraint("conference_id", "section_id", "participant_id", name="uq_application_unique"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Application id={self.id} status={self.status.value}>"


class Invitation(Base):
    """Приглашение участнику; ставится в очередь рассылки."""

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, native_enum=False, length=20),
        nullable=False,
        default=InvitationStatus.QUEUED,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped[Application] = relationship(back_populates="invitation")
    participant: Mapped[Participant] = relationship(back_populates="invitations")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Invitation id={self.id} status={self.status.value}>"


class Fee(Base):
    """Оргвзнос по заявке."""

    __tablename__ = "fees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    status: Mapped[FeeStatus] = mapped_column(
        Enum(FeeStatus, native_enum=False, length=20),
        nullable=False,
        default=FeeStatus.PENDING,
        index=True,
    )
    payment_reference: Mapped[str | None] = mapped_column(String(100), unique=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    application: Mapped[Application] = relationship(back_populates="fees")

    __table_args__ = (CheckConstraint("amount >= 0", name="ck_fee_amount_non_negative"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Fee id={self.id} amount={self.amount} status={self.status.value}>"


class Thesis(Base):
    """Тезисы доклада по заявке."""

    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str | None] = mapped_column(String(400))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_size_kb: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ThesisStatus] = mapped_column(
        Enum(ThesisStatus, native_enum=False, length=20),
        nullable=False,
        default=ThesisStatus.DRAFT,
        index=True,
    )
    reviewer_name: Mapped[str | None] = mapped_column(String(200))
    review_score: Mapped[int | None] = mapped_column(Integer)
    review_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    application: Mapped[Application] = relationship(back_populates="theses")

    __table_args__ = (
        CheckConstraint(
            "review_score IS NULL OR (review_score BETWEEN 1 AND 10)",
            name="ck_thesis_review_score_range",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Thesis id={self.id} status={self.status.value}>"


class HotelBooking(Base):
    """Потребность в гостинице по заявке."""

    __tablename__ = "hotel_bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    hotel_name: Mapped[str] = mapped_column(String(200), nullable=False)
    room_type: Mapped[str] = mapped_column(String(80), nullable=False, default="standard")
    guests_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[HotelStatus] = mapped_column(
        Enum(HotelStatus, native_enum=False, length=20),
        nullable=False,
        default=HotelStatus.REQUESTED,
        index=True,
    )
    confirmation_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    application: Mapped[Application] = relationship(back_populates="hotel_booking")

    __table_args__ = (
        CheckConstraint("check_out > check_in", name="ck_hotel_dates"),
        CheckConstraint("guests_count > 0", name="ck_hotel_guests_positive"),
    )

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HotelBooking id={self.id} status={self.status.value}>"


class AuditLog(Base):
    """Журнал значимых действий — используется для отчётов и разбора инцидентов."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.entity}.{self.action}>"


__all__ = [
    "Application",
    "ApplicationStatus",
    "AuditLog",
    "Conference",
    "Fee",
    "FeeStatus",
    "HotelBooking",
    "HotelStatus",
    "Invitation",
    "InvitationStatus",
    "Participant",
    "ParticipantRole",
    "ParticipationFormat",
    "Section",
    "Thesis",
    "ThesisStatus",
    "utcnow",
]
