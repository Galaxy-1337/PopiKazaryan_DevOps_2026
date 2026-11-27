"""Тесты участников: валидация, уникальность, поиск и разграничение доступа.

Реестр участников — раздел администратора: роль «участник» не видит его ни
списком, ни по идентификатору, ни создаёт, ни изменяет записи. Роли в реестре
больше нет: она есть только у учётной записи и определяет доступ к разделам.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import PARTICIPANT

# Служебные и зарезервированные зоны, адреса из которых недопустимы в API.
SERVICE_ZONES = {"local", "localhost", "internal", "invalid", "test"}


def test_create_participant(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/v1/participants",
        json={
            "full_name": "Смирнов Алексей Петрович",
            "email": "Smirnov@Example.com",
            "organization": "Московский Политех",
        },
    )
    assert response.status_code == 201
    body = response.json()
    # Адрес приводится к нижнему регистру — правило нормализации данных.
    assert body["email"] == "smirnov@example.com"
    # Поля роли в реестре участников больше нет.
    assert "role" not in body


def test_email_must_be_unique(admin_client: TestClient, participants: list[dict]) -> None:
    response = admin_client.post(
        "/api/v1/participants",
        json={"full_name": "Дубликат Участник", "email": participants[0]["email"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "participant_email_taken"


def test_invalid_email_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/v1/participants", json={"full_name": "Некорректный Адрес", "email": "not-an-email"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_search_participants(admin_client: TestClient, participants: list[dict]) -> None:
    response = admin_client.get("/api/v1/participants?search=user3")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_update_and_delete_participant(admin_client: TestClient, participants: list[dict]) -> None:
    participant_id = participants[0]["id"]

    updated = admin_client.patch(
        f"/api/v1/participants/{participant_id}", json={"city": "Казань", "position": "Доцент"}
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Казань"

    assert admin_client.delete(f"/api/v1/participants/{participant_id}").status_code == 204
    assert admin_client.get(f"/api/v1/participants/{participant_id}").status_code == 404


def test_list_returns_stored_participants_created_by_seed(
    admin_client: TestClient, participants: list[dict]
) -> None:
    """Список участников отдаётся целиком.

    Регрессия: адрес из служебной зоны (``.local``) в реестре ломал выдачу
    списка — строгая валидация e-mail в схеме ответа приводила к ошибке 500,
    и в веб-интерфейсе список участников оставался пустым.
    """
    response = admin_client.get("/api/v1/participants?limit=200")
    assert response.status_code == 200
    body = response.json()

    # Список не пустой и содержит всех созданных участников и демонстрационные
    # записи, которые появляются при наполнении базы.
    assert body["total"] >= len(participants) + 1
    emails = {item["email"] for item in body["items"]}
    assert {participant["email"] for participant in participants} <= emails
    # Универсальная учётная запись участника в реестре не состоит: участником
    # считается человек, данные которого указаны в заявке.
    assert PARTICIPANT[0] not in emails
    # Роли в реестре больше нет: ни в одном элементе выдачи её быть не должно.
    assert all("role" not in item for item in body["items"])


def test_account_emails_are_valid(admin_client: TestClient) -> None:
    """Адрес учётной записи и адреса реестра должны проходить проверку формата e-mail.

    Администратор в реестре участников не состоит (он не участвует в
    конференции), поэтому проверяются и его учётная запись, и выдача реестра.
    """
    me = admin_client.get("/api/v1/auth/me").json()
    listed = admin_client.get("/api/v1/participants?limit=200").json()["items"]
    emails = [me["email"], *(item["email"] for item in listed)]

    assert len(emails) > 1
    for email in emails:
        assert "@" in email
        domain = email.split("@")[-1]
        assert domain not in SERVICE_ZONES, f"адрес из служебной зоны: {email}"


def test_email_from_service_zone_is_rejected(admin_client: TestClient) -> None:
    """Адрес из служебной зоны не принимается при создании участника."""
    response = admin_client.post(
        "/api/v1/participants",
        json={"full_name": "Служебный Адрес", "email": "user@conference.local"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Разграничение доступа
# ---------------------------------------------------------------------------
def test_participant_cannot_access_registry(client: TestClient, participants: list[dict]) -> None:
    """Реестр участников закрыт роли «участник» целиком."""
    participant_id = participants[0]["id"]
    attempts = [
        client.get("/api/v1/participants"),
        client.get(f"/api/v1/participants/{participant_id}"),
        client.post(
            "/api/v1/participants",
            json={"full_name": "Новый Участник", "email": "newcomer@example.com"},
        ),
        client.patch(f"/api/v1/participants/{participant_id}", json={"city": "Казань"}),
        client.delete(f"/api/v1/participants/{participant_id}"),
    ]
    for response in attempts:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "admin_only"


def test_participant_cannot_search_registry(client: TestClient, participants: list[dict]) -> None:
    """Параметр поиска не открывает участнику доступ к чужим данным."""
    response = client.get("/api/v1/participants?search=user1&limit=200")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_only"
