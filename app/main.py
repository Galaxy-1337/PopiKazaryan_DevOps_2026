"""Точка входа приложения «Конференция».

Собирает FastAPI-приложение, подключает роутеры, обработчики ошибок,
веб-интерфейс и служебные эндпоинты.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__, database
from app.config import get_settings
from app.routers import (
    applications,
    auth_routes,
    conferences,
    participants,
    reports,
    service,
    workflow,
)
from app.seed import seed_database
from app.web import router as web_router

logger = logging.getLogger("conference")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Подготовка окружения при старте и корректное завершение."""
    settings = get_settings()
    logger.info(
        "Запуск приложения «%s» v%s (env=%s, БД=%s)",
        settings.app_name,
        __version__,
        settings.app_env,
        settings.safe_database_url,
    )
    database.create_all()
    seed_database()
    yield
    logger.info("Остановка приложения")


def _error_payload(code: str, message: str, details: list[dict] | None = None) -> dict:
    body: dict = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body


def create_app() -> FastAPI:
    """Фабрика приложения — используется uvicorn и тестами."""
    settings = get_settings()

    app = FastAPI(
        title="Конференция — API учёта участников",
        description=(
            "Учёт участников конференции, приглашений, заявок, оргвзносов, "
            "тезисов и потребности в гостинице.\n\n"
            "Документация: `/docs` (Swagger UI), `/redoc` (ReDoc), "
            "машиночитаемая схема — `/openapi.json`."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # --- Обработчики ошибок: единый формат ответа ---------------------
    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", ""),
                "type": error.get("type", ""),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload("validation_error", "Запрос содержит некорректные данные", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            payload = _error_payload(str(detail["code"]), str(detail.get("message", "")))
        else:
            payload = _error_payload("http_error", str(detail))
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(IntegrityError)
    async def integrity_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Нарушение целостности данных: %s", exc.orig)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_payload(
                "integrity_error",
                "Операция нарушает ограничения целостности данных (уникальность или ссылочную целостность)",
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Непредвиденная ошибка: %s", exc)
        message = str(exc) if settings.app_debug else "Внутренняя ошибка сервера"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload("internal_error", message),
        )

    # --- Сквозной идентификатор запроса -------------------------------
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        # Локальный запуск и контейнеры используют один и тот же адрес, поэтому
        # страница и скрипты не должны браться из кэша браузера: иначе после
        # переключения режима в браузере остаётся прежняя версия интерфейса.
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache"
        elif "text/html" in response.headers.get("content-type", ""):
            response.headers["Cache-Control"] = "no-store"
        return response

    # --- Статика и веб-интерфейс --------------------------------------
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # --- Роутеры -------------------------------------------------------
    app.include_router(service.router)
    app.include_router(auth_routes.router)
    app.include_router(conferences.router)
    app.include_router(participants.router)
    app.include_router(applications.router)
    app.include_router(workflow.router)
    app.include_router(reports.router)
    app.include_router(web_router)

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    _settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=_settings.app_host,
        port=_settings.app_port,
        reload=_settings.app_debug,
    )
