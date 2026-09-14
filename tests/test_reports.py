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
