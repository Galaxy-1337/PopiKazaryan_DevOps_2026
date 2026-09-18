"""Тесты сводного отчёта."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_report_for_empty_conference(client: TestClient, conference: dict) -> None:
    response = client.get(f"/api/v1/reports/conference/{conference['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["applications_total"] == 0
    assert body["participants_total"] == 0
    assert float(body["fees_total_amount"]) == 0.0


def test_report_aggregates_data(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[0]["id"],
            "topic": "Доклад для отчёта",
            "needs_hotel": True,
        },
    ).json()
    client.post(f"/api/v1/applications/{application['id']}/submit")
    client.post(
        f"/api/v1/applications/{application['id']}/decision",
        json={"accept": True, "comment": "Принято"},
    )
    client.post(
        "/api/v1/hotel-bookings",
        json={
            "application_id": application["id"],
            "hotel_name": "Гостиница «Семёновская»",
            "guests_count": 2,
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
        },
    )
    client.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={"title": "Тезисы для отчёта", "abstract": "г" * 90},
    )

    body = client.get(f"/api/v1/reports/conference/{conference['id']}").json()
    assert body["applications_total"] == 1
    assert body["applications_by_status"] == {"accepted": 1}
    assert body["participants_total"] == 1
    assert float(body["fees_total_amount"]) == 3000.0
    assert body["fees_by_status"] == {"pending": 1}
    assert body["theses_total"] == 1
    assert body["invitations_by_status"] == {"queued": 1}
    assert body["hotel_bookings_total"] == 1
    assert body["hotel_guests_total"] == 2


def test_report_for_unknown_conference(client: TestClient) -> None:
    response = client.get("/api/v1/reports/conference/424242")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_mailing_list_groups_accepted_participants(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Список рассылки группирует участников принятых заявок по организациям."""
    application = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[0]["id"],
            "topic": "Доклад для списка рассылки",
        },
    ).json()
    client.post(f"/api/v1/applications/{application['id']}/submit")
    client.post(
        f"/api/v1/applications/{application['id']}/decision",
        json={"accept": True, "comment": "Принято"},
    )

    body = client.get(f"/api/v1/reports/mailing-list/{conference['id']}").json()
    assert body["conference_id"] == conference["id"]
    assert body["organizations_total"] == 1
    assert body["recipients_total"] == 1
    assert body["items"][0]["organization"] == "Московский Политех"
    assert body["items"][0]["emails"] == [participants[0]["email"]]


def test_mailing_list_ignores_unaccepted_applications(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Заявки без решения и отклонённые заявки в список рассылки не попадают."""
    submitted = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[0]["id"],
            "topic": "Заявка без решения",
        },
    ).json()
    client.post(f"/api/v1/applications/{submitted['id']}/submit")

    rejected = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[1]["id"],
            "participant_id": participants[1]["id"],
            "topic": "Отклонённая заявка",
        },
    ).json()
    client.post(f"/api/v1/applications/{rejected['id']}/submit")
    client.post(
        f"/api/v1/applications/{rejected['id']}/decision",
        json={"accept": False, "comment": "Не соответствует тематике"},
    )

    body = client.get(f"/api/v1/reports/mailing-list/{conference['id']}").json()
    assert body["recipients_total"] == 0
    assert body["items"] == []


def test_mailing_list_for_unknown_conference(client: TestClient) -> None:
    response = client.get("/api/v1/reports/mailing-list/424242")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# Заполненность секций
# ---------------------------------------------------------------------------
def _create_submitted_application(
    client: TestClient,
    *,
    conference: dict,
    section_id: int,
    participant_id: int,
    topic: str,
) -> dict:
    """Создать заявку и сразу подать её — так она начинает занимать место в секции."""
    response = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": section_id,
            "participant_id": participant_id,
            "topic": topic,
        },
    )
    assert response.status_code == 201, response.text
    application = response.json()

    submitted = client.post(f"/api/v1/applications/{application['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    return application


def _section_item(body: dict, section_id: int) -> dict:
    """Выбрать строку отчёта по идентификатору секции."""
    item = next((row for row in body["items"] if row["section_id"] == section_id), None)
    assert item is not None, f"секция {section_id} отсутствует в отчёте"
    return item


def test_sections_load_counts_submitted_and_accepted(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Подана и принята заявки занимают места; у секции видно вместимость и остаток."""
    _create_submitted_application(
        client,
        conference=conference,
        section_id=sections[0]["id"],
        participant_id=participants[0]["id"],
        topic="Поданная заявка",
    )
    accepted = _create_submitted_application(
        client,
        conference=conference,
        section_id=sections[0]["id"],
        participant_id=participants[1]["id"],
        topic="Принятая заявка",
    )
    client.post(
        f"/api/v1/applications/{accepted['id']}/decision",
        json={"accept": True, "comment": "Принято"},
    )

    body = client.get(f"/api/v1/reports/sections-load/{conference['id']}").json()

    assert body["conference_id"] == conference["id"]
    assert body["sections_total"] == 3
    assert body["capacity_total"] == 9
    assert body["taken_total"] == 2
    assert body["free_total"] == 7

    loaded = _section_item(body, sections[0]["id"])
    assert loaded["title"] == sections[0]["title"]
    assert loaded["is_open"] is True
    assert loaded["capacity"] == 3
    assert loaded["submitted"] == 1
    assert loaded["accepted"] == 1
    assert loaded["taken"] == 2
    assert loaded["free_seats"] == 1
    assert loaded["is_full"] is False
    assert loaded["load_percent"] == 66.67

    empty = _section_item(body, sections[1]["id"])
    assert empty["taken"] == 0
    assert empty["free_seats"] == 3
    assert empty["load_percent"] == 0.0
    assert empty["is_full"] is False


def test_sections_load_marks_full_section_and_agrees_with_rule(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Заполненная секция помечается, и правило вместимости отклоняет лишнюю заявку."""
    for index in range(3):
        _create_submitted_application(
            client,
            conference=conference,
            section_id=sections[0]["id"],
            participant_id=participants[index]["id"],
            topic=f"Заявка {index + 1}",
        )

    body = client.get(f"/api/v1/reports/sections-load/{conference['id']}").json()
    full = _section_item(body, sections[0]["id"])
    assert full["taken"] == 3
    assert full["free_seats"] == 0
    assert full["is_full"] is True
    assert full["load_percent"] == 100.0
    assert body["free_total"] == 6

    extra = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[3]["id"],
            "topic": "Лишняя заявка",
        },
    ).json()
    blocked = client.post(f"/api/v1/applications/{extra['id']}/submit")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "section_capacity_exceeded"


def test_sections_load_stays_consistent_when_capacity_decrease_is_blocked(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Переполнение недостижимо: API не даёт уменьшить вместимость ниже занятых мест."""
    for index in range(3):
        _create_submitted_application(
            client,
            conference=conference,
            section_id=sections[0]["id"],
            participant_id=participants[index]["id"],
            topic=f"Заявка {index + 1}",
        )

    blocked = client.patch(f"/api/v1/sections/{sections[0]['id']}", json={"capacity": 2})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "section_capacity_below_load"

    body = client.get(f"/api/v1/reports/sections-load/{conference['id']}").json()
    section = _section_item(body, sections[0]["id"])
    assert section["capacity"] == 3
    assert section["taken"] == 3
    assert section["free_seats"] == 0
    assert section["is_full"] is True


def test_sections_load_ignores_rejected_and_withdrawn(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Отклонённая и отозванная заявки места не занимают."""
    rejected = _create_submitted_application(
        client,
        conference=conference,
        section_id=sections[0]["id"],
        participant_id=participants[0]["id"],
        topic="Отклонённая заявка",
    )
    client.post(
        f"/api/v1/applications/{rejected['id']}/decision",
        json={"accept": False, "comment": "Не соответствует тематике"},
    )

    withdrawn = _create_submitted_application(
        client,
        conference=conference,
        section_id=sections[0]["id"],
        participant_id=participants[1]["id"],
        topic="Отозванная заявка",
    )
    client.post(f"/api/v1/applications/{withdrawn['id']}/withdraw")

    body = client.get(f"/api/v1/reports/sections-load/{conference['id']}").json()
    section = _section_item(body, sections[0]["id"])
    assert section["submitted"] == 0
    assert section["accepted"] == 0
    assert section["taken"] == 0
    assert section["free_seats"] == 3
    assert body["taken_total"] == 0


def test_sections_load_for_unknown_conference(client: TestClient) -> None:
    response = client.get("/api/v1/reports/sections-load/424242")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
