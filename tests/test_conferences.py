"""Тесты конференций и секций: правила предметной области и разграничение доступа.

Чтение справочников доступно любой активной сессии (участнику они нужны, чтобы
выбрать секцию для заявки), изменение — только администратору.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_read_conference(admin_client: TestClient, conference: dict) -> None:
    response = admin_client.get(f"/api/v1/conferences/{conference['id']}")
    assert response.status_code == 200
    assert response.json()["slug"] == "test-conf"


def test_participant_can_read_conference_and_sections(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Справочники открыты участнику: без них он не подаст заявку."""
    conference_page = client.get(f"/api/v1/conferences/{conference['id']}")
    assert conference_page.status_code == 200
    assert conference_page.json()["slug"] == "test-conf"

    listed = client.get(f"/api/v1/sections?conference_id={conference['id']}")
    assert listed.status_code == 200
    assert listed.json()["total"] == len(sections) == 3


def test_conference_slug_must_be_unique(admin_client: TestClient, conference: dict) -> None:
    response = admin_client.post(
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


def test_conference_dates_are_validated(admin_client: TestClient) -> None:
    response = admin_client.post(
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


def test_patch_conference_rejects_reversed_dates(admin_client: TestClient, conference: dict) -> None:
    response = admin_client.patch(f"/api/v1/conferences/{conference['id']}", json={"ends_on": "2020-01-01"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_conference_dates"


def test_sections_report_free_seats(sections: list[dict]) -> None:
    assert len(sections) == 3
    assert all(section["free_seats"] == 3 for section in sections)
    assert all(section["taken_seats"] == 0 for section in sections)


def test_duplicate_section_title_is_rejected(
    admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    response = admin_client.post(
        "/api/v1/sections",
        json={"conference_id": conference["id"], "title": sections[0]["title"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "section_title_taken"


def test_conference_delete_cascades(admin_client: TestClient, conference: dict, sections: list[dict]) -> None:
    assert admin_client.delete(f"/api/v1/conferences/{conference['id']}").status_code == 204
    assert admin_client.get(f"/api/v1/sections/{sections[0]['id']}").status_code == 404


# ---------------------------------------------------------------------------
# Разграничение доступа
# ---------------------------------------------------------------------------
def test_participant_cannot_manage_conferences(client: TestClient, conference: dict) -> None:
    """Создание, изменение и удаление конференций — только администратор."""
    attempts = [
        client.post(
            "/api/v1/conferences",
            json={
                "title": "Запрещённая конференция",
                "slug": "forbidden-conf",
                "starts_on": "2026-07-01",
                "ends_on": "2026-07-02",
            },
        ),
        client.patch(f"/api/v1/conferences/{conference['id']}", json={"is_active": False}),
        client.delete(f"/api/v1/conferences/{conference['id']}"),
    ]
    for response in attempts:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


def test_participant_cannot_manage_sections(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Управление секциями и их вместимостью — только администратор."""
    attempts = [
        client.post(
            "/api/v1/sections",
            json={"conference_id": conference["id"], "title": "Запрещённая секция"},
        ),
        client.patch(f"/api/v1/sections/{sections[0]['id']}", json={"capacity": 5}),
        client.delete(f"/api/v1/sections/{sections[0]['id']}"),
    ]
    for response in attempts:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


def test_participant_cannot_change_conference_state(client: TestClient, conference: dict) -> None:
    """После запрещённых попыток конференция остаётся активной."""
    client.patch(f"/api/v1/conferences/{conference['id']}", json={"is_active": False})
    current = client.get(f"/api/v1/conferences/{conference['id']}").json()
    assert current["is_active"] is True
