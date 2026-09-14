"""Служебные маршруты: проверка работоспособности и версия."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.database import get_db
from app.models import utcnow
from app.schemas import HealthOut

router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthOut, summary="Проверка работоспособности")
def health(db: Session = Depends(get_db)) -> HealthOut:
    """Служебный адрес проверки работоспособности.

    Используется контейнерным health-check, CI и системой наблюдения.
    Возвращает ``status=degraded`` и HTTP 503, если база данных недоступна.
    """
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        db_state = "ok"
    except Exception as exc:  # noqa: BLE001 — состояние БД нужно вернуть, а не упасть
        db_state = f"error: {type(exc).__name__}"

    return HealthOut(
        status="ok" if db_state == "ok" else "degraded",
        version=__version__,
        database=db_state,
        app_env=settings.app_env,
        checked_at=utcnow(),
    )


@router.get("/version", summary="Версия приложения")
def version() -> dict[str, str]:
    """Версия приложения и окружение — для трассировки релизов."""
    settings = get_settings()
    return {"version": __version__, "app_env": settings.app_env}
