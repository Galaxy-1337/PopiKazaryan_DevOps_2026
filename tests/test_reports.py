"""Тесты сводного отчёта.

Отчёты содержат сводные данные по всем участникам, поэтому доступны только
администратору. Заявки при этом создаёт участник (каждая — от своего имени),
а решения по ним принимает администратор: роли в новой модели разделены.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable

from fastapi.testclient import TestClient

DEFAULT_TOPIC = "Доклад для отчёта"

# Учётная запись участника универсальная: данные человека передаются в заявке.
_APPLICANT_COUNTER = itertools.count(1)


def _create_application(
    participant: TestClient,
    conference: dict,
    sections: list[dict],
    *,
    topic: str = DEFAULT_TOPIC,
    section_index: int = 0,
    **overrides,
) -> dict:
    """Создать заявку от имени участника (черновик).

    Учётная запись участника универсальная, поэтому данные человека передаются в
    заявке: счётчик выдаёт разным заявкам разных людей.
    """
    number = next(_APPLICANT_COUNTER)
    payload = {
        "conference_id": conference["id"],
        "section_id": sections[section_index]["id"],
        "topic": topic,
        "format": "offline",
        "needs_hotel": False,
        "full_name": f"Заявитель Тестовый {number}",
        "email": f"applicant{number}@example.com",
    }
    payload.update(overrides)
    response = participant.post("/api/v1/applications", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _submit(participant: TestClient, application: dict) -> dict:
    """Подать заявку: место в секции занимает именно поданная заявка."""
    response = participant.post(f"/api/v1/applications/{application['id']}/submit")
    assert response.status_code == 200, response.text
    return response.json()


def _decide(admin_client: TestClient, application: dict, *, accept: bool, comment: str) -> dict:
    """Решение по заявке принимает администратор."""
    response = admin_client.post(
        f"/api/v1/applications/{application['id']}/decision",
        json={"accept": accept, "comment": comment},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _submitted_application(
    participant: TestClient,
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    *,
    topic: str,
    section_index: int = 0,
    accept: bool = False,
) -> dict:
    """Создать заявку и сразу подать её — так она начинает занимать место в секции."""
    application = _create_application(
        participant,
        conference,
        sections,
        topic=topic,
        section_index=section_index,
    )
    _submit(participant, application)
    if accept:
        return _decide(admin_client, application, accept=True, comment="Принято")
    return application


def test_report_for_empty_conference(admin_client: TestClient, conference: dict) -> None:
    response = admin_client.get(f"/api/v1/reports/conference/{conference['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["applications_total"] == 0
    assert body["participants_total"] == 0
    assert float(body["fees_total_amount"]) == 0.0


def test_report_aggregates_data(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Отчёт собирает данные одной конференции: заявки, взносы, тезисы, гостиницу."""
    application = _create_application(
        client,
        conference,
        sections,
        topic="Доклад для отчёта",
        needs_hotel=True,
    )
    _submit(client, application)
    _decide(admin_client, application, accept=True, comment="Принято")
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

    body = admin_client.get(f"/api/v1/reports/conference/{conference['id']}").json()
    assert body["applications_total"] == 1
    assert body["applications_by_status"] == {"accepted": 1}
    assert body["participants_total"] == 1
    assert float(body["fees_total_amount"]) == 3000.0
    assert body["fees_by_status"] == {"pending": 1}
    assert body["theses_total"] == 1
    assert body["invitations_by_status"] == {"queued": 1}
    assert body["hotel_bookings_total"] == 1
    assert body["hotel_guests_total"] == 2


def test_report_for_unknown_conference(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/reports/conference/424242")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_participant_cannot_read_reports(client: TestClient, conference: dict) -> None:
    """Отчёты содержат данные всех участников — роли «участник» они закрыты."""
    for path in (
        f"/api/v1/reports/conference/{conference['id']}",
        f"/api/v1/reports/sections-load/{conference['id']}",
        f"/api/v1/reports/mailing-list/{conference['id']}",
        "/api/v1/reports/invitations-queue",
    ):
        response = client.get(path)
        assert response.status_code == 403, f"{path}: {response.status_code}"
        assert response.json()["error"]["code"] == "forbidden"


def test_mailing_list_groups_accepted_participants(
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Список рассылки группирует участников принятых заявок по организациям."""
    participant = participant_factory("Сидоров Пётр Алексеевич", "mailing@example.com")
    application = _create_application(
        participant,
        conference,
        sections,
        topic="Доклад для списка рассылки",
        full_name="Сидоров Пётр Алексеевич",
        email="mailing@example.com",
    )
    _submit(participant, application)
    _decide(admin_client, application, accept=True, comment="Принято")

    body = admin_client.get(f"/api/v1/reports/mailing-list/{conference['id']}").json()
    assert body["conference_id"] == conference["id"]
    assert body["organizations_total"] == 1
    assert body["recipients_total"] == 1
    assert body["items"][0]["organization"] == "Московский Политех"
    assert body["items"][0]["emails"] == ["mailing@example.com"]


def test_mailing_list_ignores_unaccepted_applications(
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Заявки без решения и отклонённые заявки в список рассылки не попадают."""
    without_decision = participant_factory("Первый Соискатель", "waiting@example.com")
    submitted = _create_application(
        without_decision, conference, sections, topic="Заявка без решения", section_index=0
    )
    _submit(without_decision, submitted)

    rejected_participant = participant_factory("Второй Соискатель", "rejected@example.com")
    rejected = _create_application(
        rejected_participant, conference, sections, topic="Отклонённая заявка", section_index=1
    )
    _submit(rejected_participant, rejected)
    _decide(admin_client, rejected, accept=False, comment="Не соответствует тематике")

    body = admin_client.get(f"/api/v1/reports/mailing-list/{conference['id']}").json()
    assert body["recipients_total"] == 0
    assert body["items"] == []


def test_mailing_list_for_unknown_conference(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/reports/mailing-list/424242")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# Заполненность секций
# ---------------------------------------------------------------------------
def _section_item(body: dict, section_id: int) -> dict:
    """Выбрать строку отчёта по идентификатору секции."""
    item = next((row for row in body["items"] if row["section_id"] == section_id), None)
    assert item is not None, f"секция {section_id} отсутствует в отчёте"
    return item


def test_sections_load_counts_submitted_and_accepted(
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Подана и принята заявки занимают места; у секции видно вместимость и остаток."""
    first = participant_factory("Первый Участник", "load1@example.com")
    _submitted_application(first, admin_client, conference, sections, topic="Поданная заявка")

    second = participant_factory("Второй Участник", "load2@example.com")
    _submitted_application(second, admin_client, conference, sections, topic="Принятая заявка", accept=True)

    body = admin_client.get(f"/api/v1/reports/sections-load/{conference['id']}").json()

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
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Заполненная секция помечается, и правило вместимости отклоняет лишнюю заявку."""
    for index in range(3):
        participant = participant_factory(f"Участник Заполнения {index + 1}", f"full{index + 1}@example.com")
        _submitted_application(
            participant,
            admin_client,
            conference,
            sections,
            topic=f"Заявка {index + 1}",
        )

    body = admin_client.get(f"/api/v1/reports/sections-load/{conference['id']}").json()
    full = _section_item(body, sections[0]["id"])
    assert full["taken"] == 3
    assert full["free_seats"] == 0
    assert full["is_full"] is True
    assert full["load_percent"] == 100.0
    assert body["free_total"] == 6

    extra_participant = participant_factory("Лишний Участник", "overflow@example.com")
    extra = _create_application(
        extra_participant, conference, sections, topic="Лишняя заявка", section_index=0
    )
    blocked = extra_participant.post(f"/api/v1/applications/{extra['id']}/submit")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "section_capacity_exceeded"


def test_sections_load_stays_consistent_when_capacity_decrease_is_blocked(
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Переполнение недостижимо: API не даёт уменьшить вместимость ниже занятых мест."""
    for index in range(3):
        participant = participant_factory(
            f"Участник Вместимости {index + 1}", f"capacity{index + 1}@example.com"
        )
        _submitted_application(
            participant,
            admin_client,
            conference,
            sections,
            topic=f"Заявка {index + 1}",
        )

    blocked = admin_client.patch(f"/api/v1/sections/{sections[0]['id']}", json={"capacity": 2})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "section_capacity_below_load"

    body = admin_client.get(f"/api/v1/reports/sections-load/{conference['id']}").json()
    section = _section_item(body, sections[0]["id"])
    assert section["capacity"] == 3
    assert section["taken"] == 3
    assert section["free_seats"] == 0
    assert section["is_full"] is True


def test_sections_load_ignores_rejected_and_withdrawn(
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Отклонённая и отозванная заявки места не занимают."""
    rejected_participant = participant_factory("Отклонённый Участник", "rejected-load@example.com")
    rejected = _submitted_application(
        rejected_participant,
        admin_client,
        conference,
        sections,
        topic="Отклонённая заявка",
    )
    _decide(admin_client, rejected, accept=False, comment="Не соответствует тематике")

    withdrawn_participant = participant_factory("Отозванный Участник", "withdrawn@example.com")
    withdrawn = _submitted_application(
        withdrawn_participant,
        admin_client,
        conference,
        sections,
        topic="Отозванная заявка",
    )
    assert withdrawn_participant.post(f"/api/v1/applications/{withdrawn['id']}/withdraw").status_code == 200

    body = admin_client.get(f"/api/v1/reports/sections-load/{conference['id']}").json()
    section = _section_item(body, sections[0]["id"])
    assert section["submitted"] == 0
    assert section["accepted"] == 0
    assert section["taken"] == 0
    assert section["free_seats"] == 3
    assert body["taken_total"] == 0


def test_sections_load_for_unknown_conference(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/reports/sections-load/424242")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
