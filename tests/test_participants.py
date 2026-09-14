"""Тесты участников: валидация, уникальность, поиск."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_participant(client: TestClient) -> None:
    response = client.post(
        "/api/v1/participants",
        json={
            "full_name": "Смирнов Алексей Петрович",
            "email": "Smirnov@Example.com",
            "organization": "Московский Политех",
            "role": "organizer",
        },
    )
    assert response.status_code == 201
    body = response.json()
    # Адрес приводится к нижнему регистру — правило нормализации данных.
    assert body["email"] == "smirnov@example.com"
    assert body["role"] == "organizer"


def test_email_must_be_unique(client: TestClient, participants: list[dict]) -> None:
    response = client.post(
        "/api/v1/participants",
        json={"full_name": "Дубликат Участник", "email": participants[0]["email"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "participant_email_taken"


def test_invalid_email_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/participants", json={"full_name": "Некорректный Адрес", "email": "not-an-email"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_search_participants(client: TestClient, participants: list[dict]) -> None:
    response = client.get("/api/v1/participants?search=user3")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_update_and_delete_participant(client: TestClient, participants: list[dict]) -> None:
    participant_id = participants[0]["id"]

    updated = client.patch(
        f"/api/v1/participants/{participant_id}", json={"city": "Казань", "position": "Доцент"}
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Казань"

    assert client.delete(f"/api/v1/participants/{participant_id}").status_code == 204
    assert client.get(f"/api/v1/participants/{participant_id}").status_code == 404
