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
]
