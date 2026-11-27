"""Служебные маршруты: проверка работоспособности и версия.

Доступ:

* ``/health`` и ``/version`` — только администратор; участнику они закрыты
  даже после входа в систему (проверка выполняется и middleware, и зависимостью
  маршрута);
* ``/internal/health`` — служебный адрес для Docker HEALTHCHECK и CI:
  сессии не требует, но не отдаёт данных приложения (только признак
  доступности), поэтому не является способом обхода аутентификации.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__, auth
from app.config import get_settings
from app.database import get_db
from app.models import utcnow
from app.schemas import HealthOut

router = APIRouter(tags=["service"])

require_admin = auth.require_admin


def _database_state(db: Session) -> str:
    """Состояние базы данных: ``ok`` либо короткое описание ошибки."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — состояние БД нужно вернуть, а не упасть
        return f"error: {type(exc).__name__}"
    return "ok"


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Проверка работоспособности (только администратор)",
    description=(
        "Служебный адрес приложения. Требует активной сессии администратора: "
        "без входа возвращает 401, участнику — 403. Для проверок контейнера и CI "
        "используется /internal/health."
    ),
    dependencies=[Depends(require_admin)],
)
def health(db: Session = Depends(get_db)) -> HealthOut:
    """Подробное состояние приложения: версия, окружение и доступность БД."""
    settings = get_settings()
    db_state = _database_state(db)
    return HealthOut(
        status="ok" if db_state == "ok" else "degraded",
        version=__version__,
        database=db_state,
        app_env=settings.app_env,
        checked_at=utcnow(),
    )


@router.get(
    "/version",
    summary="Версия приложения (только администратор)",
    description="Версия приложения и окружение — для трассировки релизов.",
    dependencies=[Depends(require_admin)],
)
def version() -> dict[str, str]:
    settings = get_settings()
    return {"version": __version__, "app_env": settings.app_env}


@router.get(
    "/internal/health",
    include_in_schema=False,
    summary="Служебная проверка работоспособности",
)
def internal_health(db: Session = Depends(get_db)) -> JSONResponse:
    """Проверка работоспособности для контейнера и CI.

    Не требует сессии и намеренно не отдаёт ничего, кроме признака готовности:
    ни версии, ни окружения, ни сведений о базе. Возвращает 503, если база
    недоступна, — так Docker HEALTHCHECK и CI замечают сбой.
    """
    ok = _database_state(db) == "ok"
    return JSONResponse(
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ok" if ok else "degraded"},
    )
