"""Тесты конференций и секций."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_read_conference(client: TestClient, conference: dict) -> None:
    response = client.get(f"/api/v1/conferences/{conference['id']}")
    assert response.status_code == 200
    assert response.json()["slug"] == "test-conf"


def test_conference_slug_must_be_unique(client: TestClient, conference: dict) -> None:
    response = client.post(
        "/api/v1/conferences",
        json={
            "title": "Дубликат",
            "slug": conference["slug"],
            "starts_on": "2026-07-01",
            "ends_on": "2026-07-02",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conference_slug_taken"


def test_conference_dates_are_validated(client: TestClient) -> None:
    response = client.post(
        "/api/v1/conferences",
        json={
            "title": "Кривые даты",
            "slug": "bad-dates",
            "starts_on": "2026-07-10",
            "ends_on": "2026-07-01",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_patch_conference_rejects_reversed_dates(client: TestClient, conference: dict) -> None:
    response = client.patch(f"/api/v1/conferences/{conference['id']}", json={"ends_on": "2020-01-01"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_conference_dates"


def test_sections_report_free_seats(client: TestClient, sections: list[dict]) -> None:
    assert len(sections) == 3
    assert all(section["free_seats"] == 3 for section in sections)
    assert all(section["taken_seats"] == 0 for section in sections)


def test_duplicate_section_title_is_rejected(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    response = client.post(
        "/api/v1/sections",
        json={"conference_id": conference["id"], "title": sections[0]["title"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "section_title_taken"


def test_conference_delete_cascades(client: TestClient, conference: dict, sections: list[dict]) -> None:
    assert client.delete(f"/api/v1/conferences/{conference['id']}").status_code == 204
    assert client.get(f"/api/v1/sections/{sections[0]['id']}").status_code == 404
