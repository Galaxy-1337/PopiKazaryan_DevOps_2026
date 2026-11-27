"""Тесты заявок и правил предметной области, связанных с ними.

Заявки подаёт только участник и только от своего имени, решения принимает только
администратор — это и проверяется здесь наряду с доменными правилами.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable

from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from tests.conftest import PARTICIPANT, TEST_PASSWORD

# Учётная запись участника универсальная: человек определяется данными заявки.
# Счётчик выдаёт разным заявкам разных людей; там, где нужен дубликат, данные
# передаются явно.
_APPLICANT_COUNTER = itertools.count(1)


def _applicant() -> dict[str, str]:
    number = next(_APPLICANT_COUNTER)
    return {"full_name": f"Заявитель Тестовый {number}", "email": f"applicant{number}@example.com"}


def _create_application(client: TestClient, conference: dict, sections: list[dict], **overrides) -> dict:
    payload = {
        "conference_id": conference["id"],
        "section_id": sections[0]["id"],
        "topic": "Автоматизация проверок в конвейере доставки",
        "annotation": "Практический опыт внедрения обязательных проверок.",
        "format": "offline",
        "needs_hotel": False,
        **_applicant(),
    }
    payload.update(overrides)
    response = client.post("/api/v1/applications", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_new_application_is_draft(client: TestClient, conference: dict, sections: list[dict]) -> None:
    application = _create_application(client, conference, sections)
    assert application["status"] == "draft"


def test_duplicate_application_is_rejected(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    identity = {"full_name": "Дубликат Тестовый", "email": "duplicate@example.com"}
    _create_application(client, conference, sections, **identity)
    response = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "topic": "Повторная заявка",
            **identity,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "application_duplicate"


def test_same_account_can_apply_for_another_person(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Одна универсальная учётная запись — заявки на разных людей.

    Правило «одна заявка в секции» сравнивает данные участника, а не учётную
    запись: иначе из-под общей учётной записи нельзя было бы подать вторую
    заявку на другого человека.
    """
    first = _create_application(
        client,
        conference,
        sections,
        full_name="Иванов Иван Иванович",
        email="ivanov.new@example.com",
    )
    second = _create_application(
        client,
        conference,
        sections,
        full_name="Сидорова Мария Петровна",
        email="sidorova.new@example.com",
    )

    assert first["id"] != second["id"]
    assert first["participant_id"] != second["participant_id"]
    # Обе заявки видны в списке «своих»: они поданы из этой учётной записи.
    listed = client.get("/api/v1/applications?limit=200").json()["items"]
    ids = {item["id"] for item in listed}
    assert {first["id"], second["id"]} <= ids


def test_section_must_belong_to_conference(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    other = admin_client.post(
        "/api/v1/conferences",
        json={
            "title": "Другая конференция",
            "slug": "other-conf",
            "starts_on": "2026-09-01",
            "ends_on": "2026-09-02",
        },
    ).json()
    response = client.post(
        "/api/v1/applications",
        json={
            "conference_id": other["id"],
            "section_id": sections[0]["id"],
            "topic": "Чужая секция",
            **_applicant(),
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "section_not_in_conference"


def test_online_participant_cannot_request_hotel(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    response = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "topic": "Дистанционный доклад с гостиницей",
            "format": "online",
            "needs_hotel": True,
            **_applicant(),
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "hotel_not_allowed_for_online"


def test_submit_application(client: TestClient, conference: dict, sections: list[dict]) -> None:
    application = _create_application(client, conference, sections)
    response = client.post(f"/api/v1/applications/{application['id']}/submit")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None


def test_application_uses_entered_participant_data(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Данные человека берутся из заявки, а не из учётной записи.

    Учётная запись участника универсальная: ФИО и почта из формы создают (или
    находят) запись в реестре участников, а сама учётная запись остаётся
    «Пользователем».
    """
    application = _create_application(
        client,
        conference,
        sections,
        full_name="Сидорова Мария Петровна",
        email="sidorova@example.com",
        organization="НИУ ВШЭ",
        city="Санкт-Петербург",
    )

    profile = admin_client.get(f"/api/v1/participants/{application['participant_id']}").json()
    assert profile["full_name"] == "Сидорова Мария Петровна"
    assert profile["email"] == "sidorova@example.com"
    assert profile["organization"] == "НИУ ВШЭ"
    assert profile["city"] == "Санкт-Петербург"

    me = client.get("/api/v1/auth/me").json()
    # Учётная запись не меняется: она универсальная и не привязана к человеку.
    assert me["full_name"] == "Пользователь"
    assert me["email"] == PARTICIPANT[0]
    assert me["participant_id"] is None

    # Почта из заявки не является логином.
    fresh = TestClient(fastapi_app)
    assert (
        fresh.post(
            "/api/v1/auth/login", json={"email": "sidorova@example.com", "password": TEST_PASSWORD}
        ).status_code
        != 200
    )
    assert (
        fresh.post(
            "/api/v1/auth/login", json={"email": PARTICIPANT[0], "password": TEST_PASSWORD}
        ).status_code
        == 200
    )


def test_section_capacity_is_enforced(
    conference: dict,
    sections: list[dict],
    admin_client: TestClient,
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Правило предметной области: в секции ограниченное число мест."""
    clients = [
        participant_factory(f"Участник Вместимости {index}", f"capacity{index}@example.com")
        for index in range(4)
    ]

    for client in clients[:3]:
        application = _create_application(client, conference, sections)
        assert client.post(f"/api/v1/applications/{application['id']}/submit").status_code == 200

    overflow = _create_application(clients[3], conference, sections)
    response = clients[3].post(f"/api/v1/applications/{overflow['id']}/submit")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "section_capacity_exceeded"

    # Место освобождается при отклонении одной из заявок (решение администратора).
    submitted = admin_client.get(
        f"/api/v1/applications?section_id={sections[0]['id']}&status=submitted"
    ).json()["items"]
    admin_client.post(
        f"/api/v1/applications/{submitted[0]['id']}/decision",
        json={"accept": False, "comment": "Отказ"},
    )
    assert clients[3].post(f"/api/v1/applications/{overflow['id']}/submit").status_code == 200


def test_invalid_status_transition_is_rejected(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _create_application(client, conference, sections)
    # Черновик нельзя принять без подачи: решение принимает администратор.
    response = admin_client.post(f"/api/v1/applications/{application['id']}/decision", json={"accept": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"


def test_draft_cannot_be_deleted_after_submit(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _create_application(client, conference, sections)
    client.post(f"/api/v1/applications/{application['id']}/submit")
    response = client.delete(f"/api/v1/applications/{application['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "application_not_deletable"


def test_submitted_application_is_not_editable(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _create_application(client, conference, sections)
    client.post(f"/api/v1/applications/{application['id']}/submit")
    response = client.patch(f"/api/v1/applications/{application['id']}", json={"topic": "Новая тема доклада"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "application_not_editable"


def test_conference_can_be_closed_for_applications(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _create_application(client, conference, sections)
    admin_client.patch(f"/api/v1/conferences/{conference['id']}", json={"is_active": False})
    response = client.post(f"/api/v1/applications/{application['id']}/submit")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conference_inactive"


# ---------------------------------------------------------------------------
# Разграничение доступа
# ---------------------------------------------------------------------------
def test_admin_cannot_create_application(
    admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Администратор не подаёт заявки: иначе он мог бы принять её сам у себя."""
    response = admin_client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "topic": "Заявка от администратора",
            **_applicant(),
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "participant_only"


def test_participant_cannot_decide_application(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Решение по заявке принимает только администратор."""
    application = _create_application(client, conference, sections)
    client.post(f"/api/v1/applications/{application['id']}/submit")
    response = client.post(f"/api/v1/applications/{application['id']}/decision", json={"accept": True})
    assert response.status_code == 403


def test_participant_cannot_read_foreign_application(
    client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Участник не видит чужую заявку ни по адресу, ни в списке."""
    foreign_client = participant_factory("Чужой Участник", "foreign@example.com")
    foreign = _create_application(foreign_client, conference, sections)

    response = client.get(f"/api/v1/applications/{foreign['id']}")
    assert response.status_code == 403

    listed = client.get("/api/v1/applications?limit=200").json()["items"]
    assert all(item["id"] != foreign["id"] for item in listed)


def test_participant_cannot_forge_participant_id(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Подставить чужого участника в заявку нельзя: он берётся из сессии."""
    response = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[0]["id"],
            "topic": "Заявка от чужого имени",
        },
    )
    assert response.status_code == 422  # поля participant_id в схеме больше нет
