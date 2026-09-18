"""Тесты аутентификации, ролей и разграничения доступа."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import LISTENER, ORGANIZER, REVIEWER, SPEAKER


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

    users = db.query(models.User).all()
    assert users
    for user in users:
        assert user.password_hash.startswith("pbkdf2_sha256$")
        assert ORGANIZER[1] not in user.password_hash
        assert "Conference2026" not in user.password_hash


def test_password_hash_is_salted(db) -> None:  # noqa: ANN001
    """Одинаковые пароли дают разные хеши — значит используется соль."""
    from app import auth, models

    users = db.query(models.User).filter(models.User.role == models.ParticipantRole.SPEAKER).all()
    organizer = db.query(models.User).filter(models.User.role == models.ParticipantRole.ORGANIZER).one()
    assert auth.hash_password("одинаковый") != auth.hash_password("одинаковый")
    assert users and organizer  # фикстура наполнения создала учётные записи


# ---------------------------------------------------------------------------
# Справочник ролей и прав
# ---------------------------------------------------------------------------
def test_roles_endpoint_describes_permissions(anon_client: TestClient) -> None:
    """Справочник ролей показывает, что доступно каждой роли."""
    response = anon_client.get("/api/v1/auth/roles")
    assert response.status_code == 200
    roles = {item["role"]: item for item in response.json()}

    assert set(roles) == {"organizer", "listener", "speaker", "reviewer"}
    assert "application:decide" in roles["organizer"]["permissions"]
    assert "report:read" in roles["organizer"]["permissions"]
    assert "application:create" in roles["listener"]["permissions"]
    assert "thesis:submit_own" in roles["speaker"]["permissions"]
    assert "thesis:review" in roles["reviewer"]["permissions"]
    # У рецензента нет права принимать решения по заявкам и управлять взносами
    assert "application:decide" not in roles["reviewer"]["permissions"]
    assert "fee:manage" not in roles["reviewer"]["permissions"]


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


# ---------------------------------------------------------------------------
# Разграничение доступа по ролям
# ---------------------------------------------------------------------------
def test_listener_cannot_manage_conferences(listener_client: TestClient) -> None:
    response = listener_client.post(
        "/api/v1/conferences",
        json={
            "title": "Попытка слушателя",
            "slug": "listener-conf",
            "starts_on": "2026-06-01",
            "ends_on": "2026-06-02",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_listener_cannot_manage_participants(listener_client: TestClient) -> None:
    response = listener_client.post(
        "/api/v1/participants",
        json={"full_name": "Новый Участник", "email": "new@example.com"},
    )
    assert response.status_code == 403


def test_listener_cannot_decide_applications(
    listener_client: TestClient,
    client: TestClient,
    conference: dict,
    sections: list[dict],
    speaker_participant: dict,
) -> None:
    """Участник не может принять решение по заявке — это делает организатор."""
    speaker = speaker_participant
    application = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": speaker["id"],
            "topic": "Заявка для проверки прав",
        },
    ).json()
    client.post(f"/api/v1/applications/{application['id']}/submit")

    response = listener_client.post(
        f"/api/v1/applications/{application['id']}/decision", json={"accept": True}
    )
    assert response.status_code == 403


def test_reviewer_sees_theses_but_cannot_submit_them(
    reviewer_client: TestClient,
    client: TestClient,
    conference: dict,
    sections: list[dict],
    speaker_participant: dict,
) -> None:
    """Рецензент видит тезисы и оценивает их, но не подаёт свои."""
    speaker = speaker_participant
    application = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": speaker["id"],
            "topic": "Заявка для рецензента",
        },
    ).json()
    client.post(f"/api/v1/applications/{application['id']}/submit")
    client.post(f"/api/v1/applications/{application['id']}/decision", json={"accept": True})
    thesis = client.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={"title": "Тезисы для рецензии", "abstract": "а" * 80},
    ).json()

    # Читать и оценивать может
    assert reviewer_client.get("/api/v1/theses").status_code == 200
    review = reviewer_client.post(
        f"/api/v1/theses/{thesis['id']}/review",
        json={"reviewer_name": "Рецензент Тестовый", "score": 9, "accepted": True},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "accepted"

    # Подавать тезисы — нет
    response = reviewer_client.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={"title": "Свои тезисы", "abstract": "б" * 80},
    )
    assert response.status_code == 403


def test_reviewer_cannot_read_reports(reviewer_client: TestClient) -> None:
    assert reviewer_client.get("/api/v1/reports/conference/1").status_code == 403
    assert reviewer_client.get("/api/v1/reports/invitations-queue").status_code == 403


def test_listener_sees_only_own_applications(
    listener_client: TestClient,
    client: TestClient,
    conference: dict,
    sections: list[dict],
    speaker_participant: dict,
    listener_participant: dict,
) -> None:
    """Участник видит только свои заявки, даже если в системе есть другие."""
    speaker = speaker_participant
    listener = listener_participant

    for participant, topic in [(speaker, "Заявка докладчика"), (listener, "Заявка слушателя")]:
        client.post(
            "/api/v1/applications",
            json={
                "conference_id": conference["id"],
                "section_id": sections[0]["id"],
                "participant_id": participant["id"],
                "topic": topic,
            },
        )

    organizer_view = client.get("/api/v1/applications").json()
    listener_view = listener_client.get("/api/v1/applications").json()

    organizer_topics = {item["topic"] for item in organizer_view["items"]}
    listener_topics = {item["topic"] for item in listener_view["items"]}

    # Организатор видит обе заявки, слушатель — только свою
    assert {"Заявка докладчика", "Заявка слушателя"} <= organizer_topics
    assert "Заявка слушателя" in listener_topics
    assert "Заявка докладчика" not in listener_topics
    assert {item["participant_id"] for item in listener_view["items"]} == {listener_participant["id"]}


def test_listener_cannot_touch_foreign_application(
    listener_client: TestClient,
    client: TestClient,
    conference: dict,
    sections: list[dict],
    speaker_participant: dict,
) -> None:
    """Чужую заявку нельзя ни прочитать, ни подать, ни отозвать."""
    speaker = speaker_participant
    application = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": speaker["id"],
            "topic": "Чужая заявка",
        },
    ).json()

    assert listener_client.get(f"/api/v1/applications/{application['id']}").status_code == 403
    assert listener_client.post(f"/api/v1/applications/{application['id']}/submit").status_code == 403
    assert listener_client.post(f"/api/v1/applications/{application['id']}/withdraw").status_code == 403


def test_listener_cannot_create_application_for_someone_else(
    listener_client: TestClient, conference: dict, sections: list[dict], speaker_participant: dict
) -> None:
    response = listener_client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": speaker_participant["id"],
            "topic": "Заявка от чужого имени",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_foreign_participant"


def test_speaker_can_submit_own_application(
    speaker_client: TestClient, conference: dict, sections: list[dict], speaker_participant: dict
) -> None:
    """Докладчик подаёт заявку от своего имени и видит её в своём списке."""
    response = speaker_client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": speaker_participant["id"],
            "topic": "Доклад докладчика",
        },
    )
    assert response.status_code == 201, response.text

    view = speaker_client.get("/api/v1/applications").json()
    topics = [item["topic"] for item in view["items"]]
    assert "Доклад докладчика" in topics
    # Все заявки в списке принадлежат докладчику
    assert {item["participant_id"] for item in view["items"]} == {speaker_participant["id"]}


def test_speaker_cannot_decide_or_refund(
    speaker_client: TestClient, conference: dict, sections: list[dict], speaker_participant: dict
) -> None:
    application = speaker_client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": speaker_participant["id"],
            "topic": "Заявка докладчика для проверки",
        },
    ).json()
    speaker_client.post(f"/api/v1/applications/{application['id']}/submit")

    # Принять решение докладчик не может
    assert (
        speaker_client.post(
            f"/api/v1/applications/{application['id']}/decision", json={"accept": True}
        ).status_code
        == 403
    )
    # Начислить взнос тоже
    assert speaker_client.post("/api/v1/fees", json={"application_id": application["id"]}).status_code == 403


def test_listener_cannot_manage_hotel_bookings(
    listener_client: TestClient,
    client: TestClient,
    conference: dict,
    sections: list[dict],
    speaker_participant: dict,
) -> None:
    """Подтверждать бронь может только организатор."""
    speaker = speaker_participant
    application = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": speaker["id"],
            "topic": "Заявка с гостиницей",
        },
    ).json()
    client.post(f"/api/v1/applications/{application['id']}/submit")
    client.post(f"/api/v1/applications/{application['id']}/decision", json={"accept": True})
    booking = client.post(
        "/api/v1/hotel-bookings",
        json={
            "application_id": application["id"],
            "hotel_name": "Гостиница «Семёновская»",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
        },
    ).json()

    assert listener_client.post(f"/api/v1/hotel-bookings/{booking['id']}/confirm").status_code == 403
    assert listener_client.get(f"/api/v1/hotel-bookings/{booking['id']}").status_code == 403


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
        data={"email": SPEAKER[0], "password": SPEAKER[1]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "conference_session" in response.cookies

    page = anon_client.get("/")
    assert page.status_code == 200
    assert "Докладчик" in page.text
    assert "Мои заявки" in page.text

    logout = anon_client.get("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert anon_client.get("/", follow_redirects=False).status_code == 303


def test_web_login_form_shows_error_on_wrong_password(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/login",
        data={"email": LISTENER[0], "password": "неверный"},
    )
    assert response.status_code == 401
    assert "Неверный адрес электронной почты или пароль" in response.text


def test_interface_shows_only_allowed_sections(anon_client: TestClient) -> None:
    """В интерфейсе участника нет разделов организатора, и наоборот."""
    anon_client.post("/login", data={"email": REVIEWER[0], "password": REVIEWER[1]})
    reviewer_page = anon_client.get("/").text
    assert 'data-tab="theses"' in reviewer_page
    assert "Тезисы на рецензию" in reviewer_page
    assert 'data-tab="participants"' not in reviewer_page
    assert 'data-tab="finance"' not in reviewer_page
    assert 'data-tab="invitations"' not in reviewer_page
    assert "Рецензент" in reviewer_page

    anon_client.get("/logout")
    anon_client.post("/login", data={"email": ORGANIZER[0], "password": ORGANIZER[1]})
    organizer_page = anon_client.get("/").text
    for tab in ("dashboard", "applications", "finance", "invitations", "hotel", "participants"):
        assert f'data-tab="{tab}"' in organizer_page
    assert "Организатор" in organizer_page

    anon_client.get("/logout")
    anon_client.post("/login", data={"email": LISTENER[0], "password": LISTENER[1]})
    listener_page = anon_client.get("/").text
    assert "Мои заявки" in listener_page
    assert 'data-tab="participants"' not in listener_page
    assert 'data-tab="theses"' not in listener_page
