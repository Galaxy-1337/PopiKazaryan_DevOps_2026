"""Тесты аутентификации и доступа к функционалу.

Учётная запись в системе одна — организатор с полным набором прав, поэтому
проверяется её вход, состав прав и защита маршрутов без сессии.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ORGANIZER


# ---------------------------------------------------------------------------
# Вход и выход
# ---------------------------------------------------------------------------
def test_login_returns_user_and_sets_cookie(anon_client: TestClient) -> None:
    """Вход возвращает данные пользователя и устанавливает cookie сессии."""
    response = anon_client.post(
        "/api/v1/auth/login",
        json={"email": ORGANIZER[0], "password": ORGANIZER[1]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == ORGANIZER[0]
    assert body["role"] == "organizer"
    assert body["role_title"] == "Организатор"
    assert "conference_session" in response.cookies


def test_login_rejects_wrong_password(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/api/v1/auth/login",
        json={"email": ORGANIZER[0], "password": "неверный-пароль"},
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
        json={"email": ORGANIZER[0], "password": "неверный-пароль"},
    )
    assert unknown.status_code == wrong.status_code == 400
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_me_requires_login(anon_client: TestClient) -> None:
    response = anon_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_returns_current_user(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["role"] == "organizer"


def test_logout_ends_session(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_is_never_stored_in_plain_form(db) -> None:  # noqa: ANN001
    """В базе хранится только хеш пароля, а не сам пароль."""
    from app import models
    from app.config import get_settings

    settings = get_settings()
    secrets = {ORGANIZER[1], settings.demo_password, "Conference2026"}
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
    assert len(users) == 1, "в системе должна быть ровно одна учётная запись"
    assert users[0].role == models.ParticipantRole.ORGANIZER
    assert auth.hash_password("одинаковый") != auth.hash_password("одинаковый")


# ---------------------------------------------------------------------------
# Справочник учётных записей и прав
# ---------------------------------------------------------------------------
def test_roles_endpoint_describes_permissions(anon_client: TestClient) -> None:
    """Справочник показывает полный набор прав единственной учётной записи."""
    response = anon_client.get("/api/v1/auth/roles")
    assert response.status_code == 200
    roles = {item["role"]: item for item in response.json()}

    assert set(roles) == {"organizer"}
    assert roles["organizer"]["title"] == "Организатор"
    permissions = roles["organizer"]["permissions"]
    for permission in (
        "conference:manage",
        "section:manage",
        "participant:manage",
        "application:decide",
        "fee:manage",
        "invitation:manage",
        "hotel:manage",
        "thesis:review",
        "report:read",
        "user:manage",
    ):
        assert permission in permissions, f"у организатора нет права {permission}"


# ---------------------------------------------------------------------------
# Механизм прав доступа
# ---------------------------------------------------------------------------
def test_account_without_permissions_gets_forbidden(anon_client: TestClient, db) -> None:  # noqa: ANN001
    """Учётная запись без нужного права получает 403, а не данные.

    В системе есть только организатор, поэтому проверяется сам механизм прав:
    учётная запись без прав создаётся прямо в базе данных теста и удаляется
    вместе с тестовой схемой.
    """
    from app import auth, models

    user = auth.create_user(
        db,
        email="no-permissions@example.com",
        password="Conference2026",
        role=models.ParticipantRole.LISTENER,
        full_name="Учётная запись без прав",
    )
    db.add(user)
    db.commit()

    login = anon_client.post(
        "/api/v1/auth/login",
        json={"email": "no-permissions@example.com", "password": "Conference2026"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "listener"

    response = anon_client.get("/api/v1/reports/conference/1")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_seeding_removes_accounts_other_than_organizer(db) -> None:  # noqa: ANN001
    """Повторное наполнение убирает лишние учётные записи из существующей базы.

    Так база предыдущей версии приложения приводится к состоянию «одна учётная
    запись»: остальные удаляются вместе со своими сессиями.
    """
    from app import auth, models
    from app.seed import seed_database

    extra = auth.create_user(
        db,
        email="old-role@example.com",
        password="Conference2026",
        role=models.ParticipantRole.SPEAKER,
        full_name="Учётная запись прошлой версии",
    )
    db.add(extra)
    db.commit()
    assert db.query(models.User).count() == 2

    seed_database()

    users = db.query(models.User).all()
    assert len(users) == 1
    assert users[0].role == models.ParticipantRole.ORGANIZER


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
    ]:
        response = anon_client.get(path)
        assert response.status_code == 401, f"{path} доступен без входа: {response.status_code}"


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


def test_health_and_login_stay_public(anon_client: TestClient) -> None:
    """Служебные адреса и вход доступны без сессии — иначе нечем проверить сервис."""
    assert anon_client.get("/health").status_code == 200
    assert anon_client.get("/version").status_code == 200
    assert anon_client.get("/api/v1/auth/roles").status_code == 200


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
        data={"email": ORGANIZER[0], "password": ORGANIZER[1]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "conference_session" in response.cookies

    page = anon_client.get("/")
    assert page.status_code == 200
    assert "Организатор" in page.text
    assert "Заявки" in page.text

    logout = anon_client.get("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert anon_client.get("/", follow_redirects=False).status_code == 303


def test_web_login_form_shows_error_on_wrong_password(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/login",
        data={"email": ORGANIZER[0], "password": "неверный"},
    )
    assert response.status_code == 401
    assert "Неверный адрес электронной почты или пароль" in response.text


def test_interface_shows_all_application_sections(anon_client: TestClient) -> None:
    """Организатор видит все разделы приложения, включая тезисы."""
    anon_client.post("/login", data={"email": ORGANIZER[0], "password": ORGANIZER[1]})
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
    assert "Организатор" in page
