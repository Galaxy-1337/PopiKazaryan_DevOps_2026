"""Тесты заявок и правил предметной области, связанных с ними."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_application(
    client: TestClient, conference: dict, sections: list[dict], participant_id: int, **overrides
) -> dict:
    payload = {
        "conference_id": conference["id"],
        "section_id": sections[0]["id"],
        "participant_id": participant_id,
        "topic": "Автоматизация проверок в конвейере доставки",
        "annotation": "Практический опыт внедрения обязательных проверок.",
        "format": "offline",
        "needs_hotel": False,
    }
    payload.update(overrides)
    response = client.post("/api/v1/applications", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_new_application_is_draft(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _create_application(client, conference, sections, participants[0]["id"])
    assert application["status"] == "draft"


def test_duplicate_application_is_rejected(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    _create_application(client, conference, sections, participants[0]["id"])
    response = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[0]["id"],
            "topic": "Повторная заявка",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "application_duplicate"


def test_section_must_belong_to_conference(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    other = client.post(
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
            "participant_id": participants[0]["id"],
            "topic": "Чужая секция",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "section_not_in_conference"


def test_online_participant_cannot_request_hotel(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    response = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[0]["id"],
            "topic": "Дистанционный доклад с гостиницей",
            "format": "online",
            "needs_hotel": True,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "hotel_not_allowed_for_online"


def test_submit_application(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _create_application(client, conference, sections, participants[0]["id"])
    response = client.post(f"/api/v1/applications/{application['id']}/submit")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None


def test_section_capacity_is_enforced(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Правило предметной области: в секции ограниченное число мест."""
    for index in range(3):
        application = _create_application(client, conference, sections, participants[index]["id"])
        assert client.post(f"/api/v1/applications/{application['id']}/submit").status_code == 200

    overflow = _create_application(client, conference, sections, participants[3]["id"])
    response = client.post(f"/api/v1/applications/{overflow['id']}/submit")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "section_capacity_exceeded"

    # Место освобождается при отклонении одной из заявок.
    accepted_id = client.get(f"/api/v1/applications?section_id={sections[0]['id']}&status=submitted").json()[
        "items"
    ][0]["id"]
    client.post(f"/api/v1/applications/{accepted_id}/decision", json={"accept": False, "comment": "Отказ"})
    assert client.post(f"/api/v1/applications/{overflow['id']}/submit").status_code == 200


def test_invalid_status_transition_is_rejected(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _create_application(client, conference, sections, participants[0]["id"])
    # Черновик нельзя принять без подачи.
    response = client.post(f"/api/v1/applications/{application['id']}/decision", json={"accept": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"


def test_draft_cannot_be_deleted_after_submit(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _create_application(client, conference, sections, participants[0]["id"])
    client.post(f"/api/v1/applications/{application['id']}/submit")
    response = client.delete(f"/api/v1/applications/{application['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "application_not_deletable"


def test_submitted_application_is_not_editable(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _create_application(client, conference, sections, participants[0]["id"])
    client.post(f"/api/v1/applications/{application['id']}/submit")
    response = client.patch(f"/api/v1/applications/{application['id']}", json={"topic": "Новая тема доклада"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "application_not_editable"


def test_conference_can_be_closed_for_applications(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _create_application(client, conference, sections, participants[0]["id"])
    client.patch(f"/api/v1/conferences/{conference['id']}", json={"is_active": False})
    response = client.post(f"/api/v1/applications/{application['id']}/submit")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conference_inactive"
