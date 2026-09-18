"""Схемы ответов отчётных маршрутов."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class InvitationQueueItem(BaseModel):
    """Элемент очереди рассылки приглашений."""

    invitation_id: int
    status: str
    attempts: int
    email: str
    full_name: str
    subject: str


class InvitationQueueOut(BaseModel):
    """Очередь неотправленных приглашений — готова к рассылке."""

    items: list[InvitationQueueItem]
    total: Annotated[int, Field(ge=0)]


class ExpireResult(BaseModel):
    """Результат служебной операции пометки просроченных броней."""

    expired: Annotated[int, Field(ge=0)]


class SectionLoadItem(BaseModel):
    """Заполненность одной секции конференции.

    Занятыми считаются заявки в статусах «подана» и «принята» — это ровно те
    заявки, которые учитывает правило вместимости секции при приёме новой.
    Отклонённые и отозванные заявки места не занимают.
    """

    section_id: int
    title: str
    is_open: bool
    capacity: Annotated[int, Field(ge=1)]
    submitted: Annotated[int, Field(ge=0)]
    accepted: Annotated[int, Field(ge=0)]
    taken: Annotated[int, Field(ge=0)]
    free_seats: Annotated[int, Field(ge=0)]
    load_percent: Annotated[float, Field(ge=0)]
    is_full: bool


class SectionsLoadOut(BaseModel):
    """Сводка заполненности секций конференции.

    Отчёт нужен программному комитету для планирования: видно, какие секции
    заполнены, где есть свободные места и не переполнена ли секция после
    изменения вместимости.
    """

    conference_id: int
    sections_total: Annotated[int, Field(ge=0)]
    capacity_total: Annotated[int, Field(ge=0)]
    taken_total: Annotated[int, Field(ge=0)]
    free_total: Annotated[int, Field(ge=0)]
    items: list[SectionLoadItem]


class MailingListEntry(BaseModel):
    """Одна организация в списке рассылки приглашений."""

    organization: str
    participants: Annotated[int, Field(ge=0)]
    emails: list[str]


class MailingListOut(BaseModel):
    """Список рассылки, сгруппированный по организациям.

    Используется оргкомитетом для централизованной рассылки приглашений:
    письма отправляются на адреса организаций, а не каждому участнику отдельно.
    """

    conference_id: int
    organizations_total: Annotated[int, Field(ge=0)]
    recipients_total: Annotated[int, Field(ge=0)]
    items: list[MailingListEntry]


__all__ = [
    "ExpireResult",
    "InvitationQueueItem",
    "InvitationQueueOut",
    "MailingListEntry",
    "MailingListOut",
    "SectionLoadItem",
    "SectionsLoadOut",
]
