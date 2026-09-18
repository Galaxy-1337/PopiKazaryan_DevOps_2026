"""Веб-интерфейс: страница входа и рабочая страница по роли пользователя.

Интерфейс реализован на Jinja2 + ванильном JavaScript: страница получает данные
из собственного HTTP API и отображает только те разделы, которые разрешены роли
текущего пользователя.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import __version__, auth, models
from app.database import get_db

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _tabs_for(user: models.User) -> list[dict[str, str]]:
    """Разделы интерфейса, доступные учётной записи.

    В системе одна учётная запись — организатор с правом ``report:read``, поэтому
    набор разделов полный. Состав всё равно выводится из прав, а не из названия
    роли: если учётных записей с другим набором прав станет больше, интерфейс
    подстроится без правок этого модуля.
    """
    tabs: list[dict[str, str]] = [{"key": "dashboard", "title": "Сводка"}]

    if auth.has_permission(user, "report:read"):
        tabs.extend(
            [
                {"key": "applications", "title": "Заявки"},
                {"key": "finance", "title": "Оргвзносы"},
                {"key": "invitations", "title": "Приглашения"},
                {"key": "hotel", "title": "Гостиница"},
                {"key": "theses", "title": "Тезисы"},
                {"key": "participants", "title": "Участники"},
            ]
        )

    return tabs


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Страница входа. Если сессия уже активна — сразу на рабочую страницу."""
    token = request.cookies.get(auth.SESSION_COOKIE)
    if auth.current_user_from_token(db, token) is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"version": __version__, "error": None, "email": ""},
    )


@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Обработка формы входа: проверка пароля и установка cookie сессии."""
    try:
        user = auth.authenticate(db, email, password)
    except auth.AuthError as exc:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"version": __version__, "error": exc.message, "email": email},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    session = auth.start_session(db, user)
    db.commit()

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=auth.SESSION_COOKIE,
        value=session.id,
        httponly=True,
        samesite="lax",
        max_age=auth.SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return response


@router.get("/logout", include_in_schema=False)
def logout(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    """Выход из системы: удаление сессии и переход на страницу входа."""
    auth.end_session(db, request.cookies.get(auth.SESSION_COOKIE))
    db.commit()
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Рабочая страница. Без активной сессии — переход на страницу входа."""
    user = auth.current_user_from_token(db, request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "version": __version__,
            "user": user,
            "tabs": _tabs_for(user),
            "permissions": sorted(auth.PERMISSIONS.get(user.role, set())),
        },
    )
