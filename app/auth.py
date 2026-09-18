"""Аутентификация и роли пользователей.

Модуль отвечает за:

* хеширование и проверку паролей (PBKDF2-HMAC-SHA256 со случайной солью);
* создание, поиск и завершение сессий;
* определение текущего пользователя по cookie ``conference_session``;
* проверку прав доступа учётной записи (организатор — полный набор прав).

Пароли в открытом виде нигде не хранятся и не пишутся в журналы.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.config import get_settings
from app.database import get_db

# --- Параметры хеширования ------------------------------------------------
PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 200_000
SALT_BYTES = 16

# --- Параметры сессий -----------------------------------------------------
SESSION_COOKIE = "conference_session"
SESSION_TTL_HOURS = 12

# --- Права доступа --------------------------------------------------------
# В системе одна учётная запись — организатор, и она имеет полный доступ ко
# всему функционалу приложения. Права перечислены явно: так состав доступа
# виден в одном месте, его легко проверить на защите и показать через
# GET /api/v1/auth/roles.
#
# Права вида *_own означают работу только со своими данными: сервисный слой
# дополнительно фильтрует выборки по участнику, связанному с учётной записью.
PERMISSIONS: dict[models.ParticipantRole, set[str]] = {
    models.ParticipantRole.ORGANIZER: {
        "conference:manage",
        "section:manage",
        "participant:manage",
        "application:create",
        "application:read_all",
        "application:read_own",
        "application:decide",
        "fee:manage",
        "fee:read_own",
        "fee:pay_own",
        "invitation:manage",
        "invitation:read_own",
        "hotel:manage",
        "hotel:request_own",
        "thesis:read_all",
        "thesis:submit_own",
        "thesis:review",
        "report:read",
        "user:manage",
    },
}

# Названия прав для интерфейса и документации.
PERMISSION_TITLES: dict[str, str] = {
    "conference:manage": "создание и изменение конференций",
    "section:manage": "управление секциями и их вместимостью",
    "participant:manage": "ведение реестра участников",
    "application:create": "создание заявки",
    "application:read_all": "просмотр всех заявок",
    "application:read_own": "просмотр своих заявок",
    "application:decide": "решения по заявкам (принятие и отклонение)",
    "fee:manage": "начисление и возврат оргвзносов",
    "fee:read_own": "просмотр своих оргвзносов",
    "fee:pay_own": "оплата своего оргвзноса",
    "invitation:manage": "рассылка приглашений",
    "invitation:read_own": "просмотр своих приглашений",
    "hotel:manage": "управление бронями гостиницы",
    "hotel:request_own": "оформление гостиницы по своей заявке",
    "thesis:submit_own": "подача тезисов по своей заявке",
    "thesis:read_own": "просмотр своих тезисов",
    "thesis:read_all": "просмотр всех тезисов",
    "thesis:review": "рецензирование тезисов",
    "report:read": "просмотр сводных отчётов",
    "user:manage": "управление учётными записями",
}

ROLE_TITLES: dict[models.ParticipantRole, str] = {
    models.ParticipantRole.ORGANIZER: "Организатор",
}


class AuthError(Exception):
    """Ошибка аутентификации или нехватки прав."""

    def __init__(self, message: str, *, code: str = "unauthorized", status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Пароли
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Сформировать строку хранения пароля: pbkdf2_sha256$итерации$соль$хеш."""
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM, password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Проверить пароль по сохранённой строке (сравнение постоянного времени)."""
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        iterations_value = int(iterations)
    except (ValueError, AttributeError):
        return False

    if not algorithm.startswith("pbkdf2_"):
        return False

    candidate = hashlib.pbkdf2_hmac(
        algorithm.removeprefix("pbkdf2_"),
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations_value,
    )
    return hmac.compare_digest(candidate.hex(), digest)


def password_problems(password: str) -> list[str]:
    """Проверить требования к паролю. Возвращает список нарушений."""
    problems: list[str] = []
    if len(password) < 8:
        problems.append("пароль короче 8 символов")
    if not any(char.isdigit() for char in password):
        problems.append("в пароле нет цифры")
    if not any(char.isalpha() for char in password):
        problems.append("в пароле нет буквы")
    return problems


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------
def find_user(db: Session, email: str) -> models.User | None:
    """Найти пользователя по адресу электронной почты (без учёта регистра)."""
    return db.execute(
        select(models.User)
        .options(selectinload(models.User.participant))
        .where(models.User.email == email.strip().lower())
    ).scalar_one_or_none()


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: models.ParticipantRole,
    full_name: str,
    participant: models.Participant | None = None,
) -> models.User:
    """Создать учётную запись. Пароль сохраняется только в виде хеша."""
    problems = password_problems(password)
    if problems:
        raise AuthError("; ".join(problems), code="weak_password", status_code=400)

    user = models.User(
        email=email.strip().lower(),
        full_name=full_name,
        role=role,
        password_hash=hash_password(password),
        participant=participant,
        is_active=True,
    )
    db.add(user)
    return user


def authenticate(db: Session, email: str, password: str) -> models.User:
    """Проверить адрес и пароль. Возвращает пользователя либо бросает AuthError."""
    user = find_user(db, email)
    if user is None or not verify_password(password, user.password_hash):
        # Одинаковое сообщение для неизвестного адреса и неверного пароля:
        # это не подсказывает злоумышленнику, какие адреса существуют.
        raise AuthError("Неверный адрес электронной почты или пароль", code="invalid_credentials")
    if not user.is_active:
        raise AuthError("Учётная запись отключена", code="user_disabled", status_code=403)
    return user


# ---------------------------------------------------------------------------
# Сессии
# ---------------------------------------------------------------------------
def start_session(db: Session, user: models.User, *, ttl_hours: int | None = None) -> models.Session:
    """Создать сессию пользователя и вернуть её (токен — поле id)."""
    settings = get_settings()
    hours = ttl_hours if ttl_hours is not None else SESSION_TTL_HOURS
    session = models.Session(
        id=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=hours),
        app_env=settings.app_env,
    )
    db.add(session)
    user.last_login_at = datetime.now(UTC)
    return session


def current_user_from_token(db: Session, token: str | None) -> models.User | None:
    """Найти пользователя по токену сессии, если сессия существует и не истекла."""
    if not token:
        return None

    session = db.get(models.Session, token)
    if session is None:
        return None

    deadline = session.expires_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    if deadline < datetime.now(UTC):
        db.delete(session)
        db.commit()
        return None

    user = db.execute(
        select(models.User)
        .options(selectinload(models.User.participant))
        .where(models.User.id == session.user_id)
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        return None
    return user


def end_session(db: Session, token: str | None) -> None:
    """Завершить сессию (выход из системы)."""
    if not token:
        return
    session = db.get(models.Session, token)
    if session is not None:
        db.delete(session)


# ---------------------------------------------------------------------------
# Зависимости FastAPI
# ---------------------------------------------------------------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User | None:
    """Текущий пользователь или None, если вход не выполнен."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            token = header.split(" ", 1)[1].strip()
    return current_user_from_token(db, token)


def require_authenticated(user: models.User | None = Depends(get_current_user)) -> models.User:
    """Требует, чтобы пользователь вошёл в систему.

    Используется для разделов, доступных любой роли (например, справочники
    конференций и секций, которые нужны и организатору, и участнику).
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Требуется вход в систему"},
        )
    return user


def get_current_participant(user: models.User | None = Depends(get_current_user)) -> models.Participant:
    """Участник, связанный с текущим пользователем.

    Используется там, где операции выполняются «от себя»: подача заявки,
    заказ гостиницы, отправка тезисов.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Требуется вход в систему"},
        )
    if user.participant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "no_participant_profile",
                "message": "Учётная запись не связана с участником конференции",
            },
        )
    return user.participant


def has_permission(user: models.User | None, permission: str) -> bool:
    """Проверить, разрешено ли пользователю действие."""
    if user is None:
        return False
    return permission in PERMISSIONS.get(user.role, set())


def require_permission(permission: str):
    """Фабрика зависимостей: требует вход и указанное право."""

    def dependency(user: models.User | None = Depends(get_current_user)) -> models.User:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "unauthorized", "message": "Требуется вход в систему"},
            )
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "forbidden",
                    "message": (f"Учётная запись «{user.email}» не имеет права на действие «{permission}»"),
                },
            )
        return user

    return dependency


def require_any_permission(*permissions: str):
    """Требует хотя бы одно из перечисленных прав.

    Принимает именно права («report:read», «fee:manage»), а не названия ролей:
    передача названия роли — частая ошибка, поэтому она сразу отклоняется.
    """
    needed = set(permissions)
    unknown = {item for item in needed if ":" not in item}
    if unknown:
        raise ValueError(
            "require_any_permission ожидает названия прав вида «раздел:действие», "
            f"получено: {sorted(unknown)}"
        )

    def dependency(user: models.User | None = Depends(get_current_user)) -> models.User:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "unauthorized", "message": "Требуется вход в систему"},
            )
        granted = PERMISSIONS.get(user.role, set())
        if not (granted & needed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "forbidden",
                    "message": (f"Учётная запись «{user.email}» не имеет доступа к этому разделу"),
                },
            )
        return user

    return dependency


__all__ = [
    "PERMISSIONS",
    "ROLE_TITLES",
    "SESSION_COOKIE",
    "SESSION_TTL_HOURS",
    "AuthError",
    "authenticate",
    "create_user",
    "current_user_from_token",
    "end_session",
    "find_user",
    "get_current_participant",
    "get_current_user",
    "has_permission",
    "hash_password",
    "password_problems",
    "require_any_permission",
    "require_permission",
    "start_session",
    "verify_password",
]
