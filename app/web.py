"""Веб-интерфейс: страница-приложение для работы с конференцией.

Интерфейс реализован на Jinja2 + ванильном JavaScript: страница получает данные
из собственного HTTP API и отображает их в таблицах, а действия (подача заявки,
решение, оплата взноса, бронь гостиницы) выполняются через тот же API.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import __version__

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request) -> HTMLResponse:
    """Главная страница веб-интерфейса."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"version": __version__},
    )
