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


__all__ = ["ExpireResult", "InvitationQueueItem", "InvitationQueueOut"]
