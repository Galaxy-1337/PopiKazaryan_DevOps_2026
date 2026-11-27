"""Точка входа приложения «Конференция».

Собирает FastAPI-приложение, подключает роутеры, обработчики ошибок,
веб-интерфейс и служебные эндпоинты.

Доступ
------
Без активной сессии не выдаётся ничего, кроме страницы входа и статики,
необходимой этой странице. Проверка выполняется на **каждом** запросе, поэтому
прямой ввод адреса (/docs, /redoc, /openapi.json, /health, любая страница или
метод API) не даёт доступа к данным.

Служебные страницы ``/docs``, ``/redoc``, ``/openapi.json``, ``/health`` и
``/version`` доступны только администратору: у участника они закрыты даже
после входа в систему.

Единственное исключение — ``/internal/health``: служебный адрес для проверки
работоспособности контейнера и CI. Он не отдаёт данных приложения и возвращает
только признак доступности.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__, auth, database
from app.config import get_settings
from app.database import SessionLocal
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

# --- Что доступно без входа в систему -------------------------------------
# Страница входа, метод API входа, выход и статика, без которой страница входа
# не отрисуется. Всё остальное требует активной сессии.
PUBLIC_PATHS = frozenset({"/login", "/logout", "/favicon.ico", "/api/v1/auth/login"})
PUBLIC_PREFIXES = ("/static/",)

# Служебный адрес проверки работоспособности (Docker HEALTHCHECK, CI).
PROBE_PATH = "/internal/health"

# Служебные страницы приложения: только администратор.
ADMIN_ONLY_HTML_PATHS = frozenset({"/docs", "/redoc"})
ADMIN_ONLY_JSON_PATHS = frozenset({"/openapi.json", "/health", "/version"})


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


def _denied_page(message: str, status_code: int = status.HTTP_403_FORBIDDEN) -> HTMLResponse:
    """Поясняющая страница отказа для браузера (вместо «голого» JSON)."""
    return HTMLResponse(
        status_code=status_code,
        content=(
            "<!DOCTYPE html>\n"
            '<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>Доступ запрещён — Конференция</title>\n"
            '<link rel="stylesheet" href="/static/css/app.css">\n'
            "</head>\n"
            '<body class="login-page">\n'
            '<main class="login-wrap"><div class="login-card">\n'
            "<h1>Доступ запрещён</h1>\n"
            f'<div class="login-error">{message}</div>\n'
            '<p class="login-hint">Раздел доступен только администратору.</p>\n'
            '<p class="login-foot"><a href="/">Вернуться в приложение</a> · '
            '<a href="/logout">Выйти</a></p>\n'
            "</div></main>\n</body>\n</html>\n"
        ),
    )


def create_app() -> FastAPI:
    """Фабрика приложения — используется uvicorn и тестами."""
    settings = get_settings()

    app = FastAPI(
        title="Конференция — API учёта участников",
        description=(
            "Учёт участников конференции, приглашений, заявок, оргвзносов, "
            "тезисов и потребности в гостинице.\n\n"
            "Все методы требуют активной сессии. Служебные страницы "
            "(``/docs``, ``/redoc``, ``/openapi.json``, ``/health``) доступны "
            "только администратору."
        ),
        version=__version__,
        lifespan=lifespan,
        # Служебные страницы регистрируются ниже вручную: только так на них
        # можно поставить проверку роли.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
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

    # --- Проверка сессии на каждом запросе ----------------------------
    # Middleware стоит перед роутерами, поэтому ни одна страница и ни один метод
    # API не могут быть получены без входа — даже если в каком-то маршруте
    # забыта зависимость проверки прав.
    @app.middleware("http")
    async def session_guard(request: Request, call_next):
        path = request.url.path

        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES) or path == PROBE_PATH:
            return await call_next(request)

        db = SessionLocal()
        try:
            user = auth.current_user_from_token(db, auth.session_token(request))
        finally:
            db.close()

        if user is None:
            # Служебные и API-адреса отвечают кодом 401, страницы для браузера
            # перенаправляются на форму входа.
            if path.startswith("/api/") or path in ADMIN_ONLY_JSON_PATHS:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=_error_payload("unauthorized", "Требуется вход в систему"),
                )
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

        if not user.is_admin and path in ADMIN_ONLY_HTML_PATHS:
            return _denied_page(
                f"Страница «{path}» доступна только администратору. Вы вошли как «{user.role_title}»."
            )

        if not user.is_admin and path in ADMIN_ONLY_JSON_PATHS:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=_error_payload(
                    "admin_only",
                    f"Адрес «{path}» доступен только администратору (вы вошли как «{user.role_title}»)",
                ),
            )

        return await call_next(request)

    # --- Запрет кэширования интерфейса --------------------------------
    # Локальный запуск и контейнеры используют один и тот же адрес
    # (http://127.0.0.1:8000). Без этих заголовков браузер может показать
    # закэшированную страницу или старый CSS после пересборки контейнера,
    # и кажется, что изменения не применились.
    @app.middleware("http")
    async def no_cache_middleware(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            # Статика: браузер обязан проверить актуальность (ETag/Last-Modified).
            response.headers["Cache-Control"] = "no-cache"
        elif not path.startswith("/api/") and not path.startswith("/internal/"):
            # Страницы: не сохранять вовсе.
            response.headers["Cache-Control"] = "no-store"
        return response

    # --- Сквозной идентификатор запроса -------------------------------
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # --- Статика и веб-интерфейс --------------------------------------
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # --- Служебные страницы: только администратор ----------------------
    @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(auth.require_admin)])
    async def openapi_schema() -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False, dependencies=[Depends(auth.require_admin)])
    async def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=f"{settings.app_name} — API (Swagger UI)",
        )

    @app.get("/redoc", include_in_schema=False, dependencies=[Depends(auth.require_admin)])
    async def redoc_ui() -> HTMLResponse:
        return get_redoc_html(
            openapi_url="/openapi.json",
            title=f"{settings.app_name} — API (ReDoc)",
        )

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
