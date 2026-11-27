"""Маршруты аутентификации: вход, выход и сведения о текущем пользователе.

Доступ:

* ``POST /login`` — единственный метод API, открытый без сессии (иначе войти
  было бы невозможно). Проверка сессии для всех остальных адресов выполняется
  в middleware приложения;
* ``GET /me`` и ``POST /logout`` — для любой активной сессии;
* ``GET /roles`` — справочник прав, доступен только администратору.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app import auth, models, schemas, services
from app.database import get_db
from app.routers.deps import bad_request

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=schemas.CurrentUserOut,
    summary="Вход в систему",
    description=(
        "Проверяет адрес электронной почты и пароль, создаёт сессию и устанавливает "
        "cookie conference_session. Пароль передаётся только по защищённому соединению "
        "и нигде не сохраняется в открытом виде. Это единственный адрес, доступный "
        "без активной сессии."
    ),
)
def login(
    payload: schemas.LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> models.User:
    try:
        user = auth.authenticate(db, payload.email, payload.password)
    except auth.AuthError as exc:
        raise bad_request(exc.code, exc.message) from exc

    session = auth.start_session(db, user)
    services.log_action(
        db,
        entity="user",
        entity_id=user.id,
        action="login",
        details=f"роль: {user.role_title}",
    )
    db.commit()
    db.refresh(user)

    response.set_cookie(
        key=auth.SESSION_COOKIE,
        value=session.id,
        httponly=True,
        samesite="lax",
        max_age=auth.SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return user


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Выход из системы",
    description="Удаляет сессию и очищает cookie.",
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _user: models.User = Depends(auth.require_authenticated),
) -> dict[str, str]:
    auth.end_session(db, auth.session_token(request))
    db.commit()
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


@router.get(
    "/me",
    response_model=schemas.CurrentUserOut,
    summary="Текущий пользователь",
    description="Возвращает учётную запись текущей сессии либо ошибку 401.",
)
def me(user: models.User = Depends(auth.require_authenticated)) -> models.User:
    return user


@router.get(
    "/roles",
    response_model=list[schemas.RoleOut],
    summary="Роли и их права (только администратор)",
    description=(
        "Справочник ролей: какие действия доступны администратору и участнику. "
        "Доступен только администратору — участнику этот раздел закрыт."
    ),
)
def roles(_user: models.User = Depends(auth.require_admin)) -> list[schemas.RoleOut]:
    return [
        schemas.RoleOut(
            role=role,
            title=auth.ROLE_TITLES.get(role, str(role)),
            permissions=sorted(permissions),
        )
        for role, permissions in auth.PERMISSIONS.items()
    ]
