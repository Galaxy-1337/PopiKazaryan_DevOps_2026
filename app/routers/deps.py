"""Общие вспомогательные функции HTTP-слоя."""

from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.schemas import Page

T = TypeVar("T")


def not_found(entity: str, entity_id: int) -> HTTPException:
    """Единообразный ответ 404."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "not_found", "message": f"{entity} с идентификатором {entity_id} не найден"},
    )


def conflict(code: str, message: str, http_status: int = status.HTTP_409_CONFLICT) -> HTTPException:
    """Единообразный ответ 409 (нарушение правила предметной области)."""
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def bad_request(code: str, message: str) -> HTTPException:
    """Единообразный ответ 400 (некорректный запрос)."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": code, "message": message})


def paginate(db: Session, stmt: Select, *, limit: int, offset: int, schema: type[T]) -> Page[T]:
    """Выполнить запрос с пагинацией и вернуть страницу результатов."""
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return Page[schema](
        items=[schema.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


__all__ = ["bad_request", "conflict", "not_found", "paginate"]
