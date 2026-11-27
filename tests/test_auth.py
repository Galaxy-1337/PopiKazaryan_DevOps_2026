"""Тесты аутентификации и разграничения доступа.

В системе две роли — администратор и участник, поэтому проверяется:

* вход, выход и единый формат ошибки при неверных данных;
* справочник ролей: ровно две роли с ожидаемым набором прав;
* механизм прав: отсутствие нужного права даёт 403, а не данные;
* закрытость всего функционала без активной сессии (кроме страницы входа и
  служебного пробника ``/internal/health``);
* недоступность служебных страниц (``/docs``, ``/redoc``, ``/openapi.json``,
  ``/health``, ``/version``) роли «участник».
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN, PARTICIPANT

# Ожидаемый состав прав ролей (app.auth.PERMISSIONS).
ADMIN_PERMISSIONS = {
    "conference:manage",
    "section:manage",
    "participant:read",
    "application:read_all",
    "application:decide",
    "invitation:manage",
    "fee:read_all",
    "fee:manage",
    "hotel:read_all",
    "hotel:manage",
    "thesis:read_all",
    "thesis:review",
    "report:read",
    "service:read",
    "user:manage",
}

PARTICIPANT_PERMISSIONS = {
    "catalog:read",
    "application:create",
    "application:read_own",
    "application:withdraw_own",
    "fee:read_own",
    "fee:pay_own",
    "fee:refund_own",
    "hotel:read_own",
    "hotel:request_own",
    "thesis:read_own",
    "thesis:submit_own",
}


# ---------------------------------------------------------------------------
# Вход и выход
# ---------------------------------------------------------------------------
def test_login_returns_admin_and_sets_cookie(anon_client: TestClient) -> None:
    """Вход администратора возвращает данные пользователя и cookie сессии."""
    response = anon_client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN[0], "password": ADMIN[1]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == ADMIN[0]
    assert body["role"] == "admin"
    assert body["role_title"] == "Администратор"
    assert body["participant_id"] is None  # администратор не участвует в конференции
    assert "conference_session" in response.cookies


def test_login_returns_universal_participant_account(anon_client: TestClient) -> None:
    """Учётная запись участника универсальная и не привязана к человеку.

    Кто именно участвует в конференции, определяется данными конкретной заявки
    (ФИО и почта), поэтому профиль участника у учётной записи отсутствует.
    """
    response = anon_client.post(
        "/api/v1/auth/login",
        json={"email": PARTICIPANT[0], "password": PARTICIPANT[1]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == PARTICIPANT[0]
    assert body["role"] == "participant"
    assert body["role_title"] == "Участник"
    assert body["participant_id"] is None


def test_login_rejects_wrong_password(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN[0], "password": "неверный-пароль"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_does_not_reveal_existing_email(anon_client: TestClient) -> None:
    """Одинаковый ответ на неизвестный адрес и неверный пароль."""
    unknown = anon_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "любой-пароль"},
    )
    wrong = anon_client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN[0], "password": "неверный-пароль"},
    )
    assert unknown.status_code == wrong.status_code == 400
    assert unknown.json()["error"]["code"] == wrong.json()["error"]["code"] == "invalid_credentials"
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_me_requires_login(anon_client: TestClient) -> None:
    response = anon_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_returns_current_user(admin_client: TestClient, participant_client: TestClient) -> None:
    admin = admin_client.get("/api/v1/auth/me")
    assert admin.status_code == 200
    assert admin.json()["role"] == "admin"

    participant = participant_client.get("/api/v1/auth/me")
    assert participant.status_code == 200
    assert participant.json()["role"] == "participant"


def test_logout_ends_session(admin_client: TestClient) -> None:
    assert admin_client.get("/api/v1/auth/me").status_code == 200
    assert admin_client.post("/api/v1/auth/logout").status_code == 200
    assert admin_client.get("/api/v1/auth/me").status_code == 401


def test_password_is_never_stored_in_plain_form(db) -> None:  # noqa: ANN001
    """В базе хранится только хеш пароля, а не сам пароль."""
    from app import models
    from app.config import get_settings

    settings = get_settings()
    secrets = {ADMIN[1], PARTICIPANT[1], settings.demo_password, "Conference2026"}
    users = db.query(models.User).all()
    assert users
    for user in users:
        assert user.password_hash.startswith("pbkdf2_sha256$")
        for secret in secrets:
            assert secret not in user.password_hash


def test_password_hash_is_salted(db) -> None:  # noqa: ANN001
    """Одинаковые пароли дают разные хеши — значит используется соль."""
    from app import auth, models

    users = db.query(models.User).all()
    assert len(users) == 2, "в системе должны быть ровно две учётные записи"
    assert {user.role for user in users} == {models.UserRole.ADMIN, models.UserRole.PARTICIPANT}
    assert auth.hash_password("одинаковый") != auth.hash_password("одинаковый")


# ---------------------------------------------------------------------------
# Справочник ролей и прав
# ---------------------------------------------------------------------------
def test_roles_endpoint_describes_two_roles(admin_client: TestClient) -> None:
    """Справочник показывает ровно две роли и полный состав их прав."""
    response = admin_client.get("/api/v1/auth/roles")
    assert response.status_code == 200

    roles = {item["role"]: item for item in response.json()}
    assert set(roles) == {"admin", "participant"}
    assert roles["admin"]["title"] == "Администратор"
    assert roles["participant"]["title"] == "Участник"
    assert set(roles["admin"]["permissions"]) == ADMIN_PERMISSIONS
    assert set(roles["participant"]["permissions"]) == PARTICIPANT_PERMISSIONS

    # Прав прежней модели (роль была и у участника реестра) в справочнике нет.
    for stale in ("participant:manage", "invitation:read_own", "organizer"):
        assert stale not in roles["admin"]["permissions"]
        assert stale not in roles["participant"]["permissions"]


def test_roles_endpoint_is_admin_only(participant_client: TestClient, anon_client: TestClient) -> None:
    """Справочник ролей — раздел администратора."""
    forbidden = participant_client.get("/api/v1/auth/roles")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "admin_only"

    unauthorized = anon_client.get("/api/v1/auth/roles")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "unauthorized"


def test_permission_mechanism_closes_reports_to_participant(
    participant_client: TestClient, admin_client: TestClient
) -> None:
    """У участника нет права report:read — раздел закрыт, у администратора открыт."""
    response = participant_client.get("/api/v1/reports/conference/1")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    allowed = admin_client.get("/api/v1/reports/conference/1")
    assert allowed.status_code == 200


def test_seeding_keeps_exactly_two_accounts(db) -> None:  # noqa: ANN001
    """Повторное наполнение убирает лишние учётные записи из существующей базы.

    Так база предыдущей версии приложения (с ролями участника реестра)
    приводится к состоянию «две учётные записи»: лишние удаляются вместе со
    своими сессиями.
    """
    from app import auth, models
    from app.seed import seed_database

    extra = auth.create_user(
        db,
        email="old-role@example.com",
        password="Conference2026",
        role=models.UserRole.PARTICIPANT,
        full_name="Учётная запись прошлой версии",
    )
    db.add(extra)
    db.commit()
    assert db.query(models.User).count() == 3

    seed_database()
    db.expire_all()

    users = db.query(models.User).all()
    assert len(users) == 2
    assert {user.role for user in users} == {models.UserRole.ADMIN, models.UserRole.PARTICIPANT}
    assert {user.email for user in users} == {ADMIN[0], PARTICIPANT[0]}


# ---------------------------------------------------------------------------
# Защита маршрутов без входа
# ---------------------------------------------------------------------------
def test_anonymous_cannot_read_any_data(anon_client: TestClient) -> None:
    for path in [
        "/api/v1/conferences",
        "/api/v1/sections",
        "/api/v1/participants",
        "/api/v1/applications",
        "/api/v1/fees",
        "/api/v1/invitations",
        "/api/v1/theses",
        "/api/v1/hotel-bookings",
        "/api/v1/reports/conference/1",
        "/api/v1/reports/sections-load/1",
        "/api/v1/reports/mailing-list/1",
        "/api/v1/reports/invitations-queue",
        "/api/v1/auth/me",
        "/api/v1/auth/roles",
    ]:
        response = anon_client.get(path)
        assert response.status_code == 401, f"{path} доступен без входа: {response.status_code}"
        assert response.json()["error"]["code"] == "unauthorized"


def test_anonymous_cannot_create_data(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/api/v1/conferences",
        json={
            "title": "Без входа",
            "slug": "anon-conf",
            "starts_on": "2026-06-01",
            "ends_on": "2026-06-02",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_web_paths_without_session_redirect_to_login(anon_client: TestClient) -> None:
    """Любая страница браузера без сессии ведёт на форму входа."""
    for path in ("/", "/docs", "/redoc", "/favicon.ico-not-found"):
        response = anon_client.get(path, follow_redirects=False)
        assert response.status_code == 303, f"{path}: {response.status_code}"
        assert response.headers["location"] == "/login"


# ---------------------------------------------------------------------------
# Служебные страницы: администратору открыты, участнику закрыты,
# служебный пробник доступен всем
# ---------------------------------------------------------------------------
def test_internal_health_is_public(anon_client: TestClient, participant_client: TestClient) -> None:
    """Пробник контейнера и CI не требует сессии и не отдаёт данных приложения."""
    for client in (anon_client, participant_client):
        response = client.get("/internal/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_admin_can_open_service_pages(admin_client: TestClient) -> None:
    assert admin_client.get("/docs").status_code == 200
    assert admin_client.get("/redoc").status_code == 200
    assert admin_client.get("/openapi.json").status_code == 200
    assert admin_client.get("/health").status_code == 200
    assert admin_client.get("/version").status_code == 200


def test_participant_cannot_open_service_pages(participant_client: TestClient) -> None:
    """Служебные страницы закрыты участнику даже после входа в систему."""
    for path in ("/docs", "/redoc"):
        response = participant_client.get(path)
        assert response.status_code == 403, f"{path}: {response.status_code}"
        assert "Доступ запрещён" in response.text

    for path in ("/openapi.json", "/health", "/version"):
        response = participant_client.get(path)
        assert response.status_code == 403, f"{path}: {response.status_code}"
        assert response.json()["error"]["code"] == "admin_only"


def test_anonymous_cannot_open_service_pages(anon_client: TestClient) -> None:
    for path in ("/docs", "/redoc"):
        response = anon_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    for path in ("/openapi.json", "/health", "/version"):
        response = anon_client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


# ---------------------------------------------------------------------------
# Веб-интерфейс
# ---------------------------------------------------------------------------
def test_web_login_page_is_public_and_root_requires_login(anon_client: TestClient) -> None:
    """Страница входа доступна всем, рабочая страница — только после входа."""
    login_page = anon_client.get("/login", follow_redirects=False)
    assert login_page.status_code == 200
    assert "Вход в систему" in login_page.text

    root = anon_client.get("/", follow_redirects=False)
    assert root.status_code == 303
    assert root.headers["location"] == "/login"


def test_web_login_form_authenticates_and_logs_out(anon_client: TestClient) -> None:
    """Вход через форму устанавливает cookie, выход — удаляет."""
    response = anon_client.post(
        "/login",
        data={"email": ADMIN[0], "password": ADMIN[1]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "conference_session" in response.cookies

    page = anon_client.get("/")
    assert page.status_code == 200
    assert "Администратор" in page.text
    assert "Заявки" in page.text

    logout = anon_client.get("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert anon_client.get("/", follow_redirects=False).status_code == 303


def test_web_login_form_shows_error_on_wrong_password(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/login",
        data={"email": ADMIN[0], "password": "неверный"},
    )
    assert response.status_code == 401
    assert "Неверный адрес электронной почты или пароль" in response.text


def test_admin_interface_shows_all_application_sections(anon_client: TestClient) -> None:
    """Администратор видит все разделы приложения, включая тезисы."""
    anon_client.post("/login", data={"email": ADMIN[0], "password": ADMIN[1]})
    page = anon_client.get("/").text

    for tab in (
        "dashboard",
        "applications",
        "finance",
        "invitations",
        "hotel",
        "theses",
        "participants",
    ):
        assert f'data-tab="{tab}"' in page
    assert "Администратор" in page


def test_participant_interface_hides_admin_sections(participant_client: TestClient) -> None:
    """Участник видит только свои разделы: сводка, приглашения и реестр скрыты."""
    page = participant_client.get("/").text

    for tab in ("applications", "finance", "hotel", "theses"):
        assert f'data-tab="{tab}"' in page
    for hidden in ("dashboard", "invitations", "participants"):
        assert f'data-tab="{hidden}"' not in page
    assert "Участник" in page
    assert "Мои заявки" in page
