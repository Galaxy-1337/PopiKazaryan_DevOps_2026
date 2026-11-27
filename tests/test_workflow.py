"""Тесты оргвзносов, приглашений, тезисов и гостиницы.

Роли в новой модели разделены: действия участника (``client``) выполняет
участник, решения администратора (``admin_client``) — администратор. Разделы
«приглашения», начисление взносов и оценивание тезисов закрыты участнику;
заявки, тезисы и гостиницу оформляет только участник — и только от своего имени.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import timedelta

from fastapi.testclient import TestClient

from app import models

DEFAULT_TOPIC = "Практика непрерывной доставки изменений"

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
    response = participant.post(f"/api/v1/applications/{application['id']}/submit")
    assert response.status_code == 200, response.text
    return response.json()


def _accept(admin_client: TestClient, application: dict, comment: str = "Принято") -> dict:
    """Решение администратора: принятие начисляет взнос и ставит приглашение в очередь."""
    response = admin_client.post(
        f"/api/v1/applications/{application['id']}/decision",
        json={"accept": True, "comment": comment},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _accepted_application(
    participant: TestClient,
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    **overrides,
) -> dict:
    """Создать заявку и довести её до статуса «принята»."""
    application = _create_application(participant, conference, sections, **overrides)
    _submit(participant, application)
    return _accept(admin_client, application)


def _own_fee(participant: TestClient, application: dict) -> dict:
    """Взнос по заявке: участник видит только взносы по своим заявкам."""
    fees = participant.get(f"/api/v1/fees?application_id={application['id']}").json()["items"]
    assert len(fees) == 1, fees
    return fees[0]


def _hotel_payload(application: dict, **overrides) -> dict:
    payload = {
        "application_id": application["id"],
        "hotel_name": "Гостиница «Семёновская»",
        "room_type": "standard",
        "guests_count": 1,
        "check_in": "2026-06-01",
        "check_out": "2026-06-03",
    }
    payload.update(overrides)
    return payload


def _create_thesis(participant: TestClient, application: dict, *, title: str) -> dict:
    response = participant.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={"title": title, "abstract": "а" * 80},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Оргвзносы
# ---------------------------------------------------------------------------
def test_fee_is_charged_automatically_on_acceptance(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Правило: при принятии заявки оргвзнос начисляется автоматически."""
    application = _accepted_application(client, admin_client, conference, sections)
    fees = client.get(f"/api/v1/fees?application_id={application['id']}").json()["items"]
    assert len(fees) == 1
    assert float(fees[0]["amount"]) == 3000.0
    assert fees[0]["status"] == "pending"
    # Новое поле ответа: участник видит статус заявки, к которой относится взнос.
    assert fees[0]["application_status"] == "accepted"


def test_fee_cannot_be_charged_for_draft(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    draft = _create_application(client, conference, sections, topic="Черновик без решения")
    response = admin_client.post("/api/v1/fees", json={"application_id": draft["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fee_requires_accepted_application"


def test_participant_cannot_charge_fee(client: TestClient, conference: dict, sections: list[dict]) -> None:
    """Начисление оргвзноса — операция администратора."""
    draft = _create_application(client, conference, sections, topic="Черновик для начисления")
    response = client.post("/api/v1/fees", json={"application_id": draft["id"]})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_only"


def test_pay_and_refund_fee(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections)
    fee = _own_fee(client, application)

    paid = client.post(f"/api/v1/fees/{fee['id']}/pay", json={"payment_reference": "PAY-0001"})
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"

    # Повторная оплата невозможна.
    again = client.post(f"/api/v1/fees/{fee['id']}/pay", json={})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "fee_already_paid"

    # Возврат возможен только по отозванной или отклонённой заявке.
    early = client.post(f"/api/v1/fees/{fee['id']}/refund", json={"reason": "Передумал"})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "refund_not_allowed_for_status"

    client.post(f"/api/v1/applications/{application['id']}/withdraw")
    refunded = client.post(f"/api/v1/fees/{fee['id']}/refund", json={"reason": "Отказ участника"})
    assert refunded.status_code == 200
    assert refunded.json()["status"] == "refunded"
    assert refunded.json()["application_status"] == "withdrawn"


def test_refund_requires_paid_fee(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections)
    fee = _own_fee(client, application)
    response = client.post(f"/api/v1/fees/{fee['id']}/refund", json={"reason": "Не оплачен"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fee_not_paid"


def test_participant_cannot_pay_foreign_fee(
    client: TestClient,
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Участник оплачивает и возвращает только взносы по своим заявкам."""
    application = _accepted_application(client, admin_client, conference, sections)
    fee = _own_fee(client, application)

    foreign = participant_factory("Чужой Плательщик", "foreign-fee@example.com")
    assert foreign.post(f"/api/v1/fees/{fee['id']}/pay", json={}).status_code == 403
    assert foreign.post(f"/api/v1/fees/{fee['id']}/refund", json={"reason": "Чужой взнос"}).status_code == 403
    # Администратор может отметить оплату любого взноса.
    assert admin_client.post(f"/api/v1/fees/{fee['id']}/pay", json={}).status_code == 200


# ---------------------------------------------------------------------------
# Приглашения (раздел администратора)
# ---------------------------------------------------------------------------
def test_invitation_is_queued_on_acceptance(
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """У нового участника ровно одно приглашение — по принятой заявке."""
    participant = participant_factory("Приглашённый Участник", "invited@example.com")
    application = _accepted_application(participant, admin_client, conference, sections)

    items = admin_client.get(f"/api/v1/invitations?participant_id={application['participant_id']}").json()[
        "items"
    ]
    assert len(items) == 1
    assert items[0]["status"] == "queued"
    assert application["id"] == items[0]["application_id"]


def test_participant_cannot_manage_invitations(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Приглашения — раздел администратора: участнику он закрыт целиком."""
    application = _create_application(client, conference, sections, topic="Заявка для приглашения")
    attempts = [
        client.get("/api/v1/invitations"),
        client.post("/api/v1/invitations", json={"application_id": application["id"]}),
        client.post("/api/v1/invitations/1/send"),
    ]
    for response in attempts:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "admin_only"


def test_invitation_queue_report_lists_pending(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Созданное приглашение появляется в очереди рассылки."""
    application = _accepted_application(client, admin_client, conference, sections)
    queue = admin_client.get("/api/v1/reports/invitations-queue").json()

    # В очередь попадает участник заявки (человек из данных заявки), а не
    # универсальная учётная запись.
    participant = admin_client.get(f"/api/v1/participants/{application['participant_id']}").json()
    emails = [item["email"] for item in queue["items"]]
    assert participant["email"] in emails
    # В очереди только приглашения в статусе «в очереди» и с ошибкой отправки
    assert queue["total"] == len(queue["items"])


def test_send_invitation_success_and_failure(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections)
    invitations = admin_client.get(
        f"/api/v1/invitations?participant_id={application['participant_id']}"
    ).json()["items"]
    invitation = next(item for item in invitations if item["application_id"] == application["id"])

    failed = admin_client.post(f"/api/v1/invitations/{invitation['id']}/send?success=false&error=SMTP")
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["attempts"] == 1

    # Повторная отправка после ошибки разрешена (очередь рассылки).
    sent = admin_client.post(f"/api/v1/invitations/{invitation['id']}/send?success=true")
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert sent.json()["attempts"] == 2


def test_duplicate_invitation_is_rejected(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections)
    response = admin_client.post("/api/v1/invitations", json={"application_id": application["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invitation_exists"


# ---------------------------------------------------------------------------
# Тезисы
# ---------------------------------------------------------------------------
def test_theses_require_accepted_application(
    client: TestClient, conference: dict, sections: list[dict]
) -> None:
    draft = _create_application(client, conference, sections, topic="Черновик для тезисов")
    response = client.post(
        f"/api/v1/applications/{draft['id']}/theses",
        json={"title": "Тезисы", "abstract": "а" * 60},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "thesis_requires_accepted_application"


def test_thesis_review_threshold(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Правило: тезисы принимаются при оценке не ниже 6 баллов."""
    application = _accepted_application(client, admin_client, conference, sections)
    response = client.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={
            "title": "Непрерывная доставка изменений",
            "abstract": "Описание практики внедрения конвейера доставки изменений в учебном проекте.",
            "keywords": "CI/CD, DevOps",
            "file_name": "thesis.pdf",
            "file_size_kb": 120,
        },
    )
    assert response.status_code == 201, response.text
    thesis = response.json()
    assert thesis["status"] == "submitted"

    low = admin_client.post(
        f"/api/v1/theses/{thesis['id']}/review",
        json={"reviewer_name": "Рецензент Тестовый", "score": 4, "accepted": True},
    )
    assert low.status_code == 200
    assert low.json()["status"] == "rejected"


def test_thesis_accepted_with_good_score(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections)
    thesis = _create_thesis(client, application, title="Тезисы доклада")
    good = admin_client.post(
        f"/api/v1/theses/{thesis['id']}/review",
        json={"reviewer_name": "Рецензент Тестовый", "score": 9, "accepted": True},
    )
    assert good.status_code == 200
    assert good.json()["status"] == "accepted"


def test_thesis_score_is_validated(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections)
    thesis = _create_thesis(client, application, title="Тезисы для проверки оценки")
    response = admin_client.post(
        f"/api/v1/theses/{thesis['id']}/review",
        json={"reviewer_name": "Рецензент Тестовый", "score": 11},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_participant_cannot_review_thesis(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Оценивает тезисы только администратор."""
    application = _accepted_application(client, admin_client, conference, sections)
    thesis = _create_thesis(client, application, title="Тезисы без рецензента")
    response = client.post(
        f"/api/v1/theses/{thesis['id']}/review",
        json={"reviewer_name": "Сам Себе Рецензент", "score": 10},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_only"


def test_admin_cannot_submit_thesis(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Администратор тезисы не пишет: это действие участника по своей заявке."""
    application = _accepted_application(client, admin_client, conference, sections)
    response = admin_client.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={"title": "Тезисы администратора", "abstract": "б" * 80},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "participant_only"


def test_participant_cannot_read_or_write_foreign_thesis(
    client: TestClient,
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Чужие тезисы недоступны ни по адресу, ни в списке, ни для правки."""
    foreign = participant_factory("Чужой Автор", "foreign-thesis@example.com")
    foreign_application = _accepted_application(foreign, admin_client, conference, sections, section_index=1)
    thesis = _create_thesis(foreign, foreign_application, title="Чужие тезисы")

    assert client.get(f"/api/v1/theses/{thesis['id']}").status_code == 403
    forbidden = client.post(
        f"/api/v1/applications/{foreign_application['id']}/theses",
        json={"title": "Подмена тезисов", "abstract": "в" * 80},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden_not_owner"

    listed = client.get("/api/v1/theses?limit=200").json()["items"]
    assert all(item["id"] != thesis["id"] for item in listed)
    # Администратор видит тезисы всех участников.
    assert admin_client.get(f"/api/v1/theses/{thesis['id']}").status_code == 200


# ---------------------------------------------------------------------------
# Гостиница
# ---------------------------------------------------------------------------
def test_hotel_booking_lifecycle(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Запрос оформляет участник, подтверждает — администратор."""
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    booking = client.post("/api/v1/hotel-bookings", json=_hotel_payload(application))
    assert booking.status_code == 201, booking.text
    body = booking.json()
    assert body["status"] == "requested"
    assert body["nights"] == 2

    # Подтверждение брони — решение администратора.
    denied = client.post(f"/api/v1/hotel-bookings/{body['id']}/confirm")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "admin_only"

    confirmed = admin_client.post(f"/api/v1/hotel-bookings/{body['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


def test_admin_cannot_create_hotel_booking(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Администратор бронь не оформляет: это действие участника."""
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    response = admin_client.post("/api/v1/hotel-bookings", json=_hotel_payload(application))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "participant_only"


def test_hotel_dates_must_be_within_conference(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    response = client.post(
        "/api/v1/hotel-bookings",
        json=_hotel_payload(application, check_in="2026-05-20", check_out="2026-05-22"),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "hotel_dates_out_of_conference"


def test_hotel_not_available_for_online_format(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections, format="online")
    response = client.post("/api/v1/hotel-bookings", json=_hotel_payload(application))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "hotel_not_allowed_for_online"


def test_second_hotel_booking_is_rejected(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    payload = _hotel_payload(application)
    assert client.post("/api/v1/hotel-bookings", json=payload).status_code == 201
    duplicate = client.post("/api/v1/hotel-bookings", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "hotel_booking_exists"


def test_participant_cannot_book_foreign_application(
    client: TestClient,
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Участник оформляет гостиницу только по своей заявке."""
    foreign = participant_factory("Чужой Гость", "foreign-hotel@example.com")
    foreign_application = _accepted_application(
        foreign, admin_client, conference, sections, section_index=1, needs_hotel=True
    )
    response = client.post("/api/v1/hotel-bookings", json=_hotel_payload(foreign_application))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_not_owner"


def test_participant_sees_only_own_hotel_bookings(
    client: TestClient,
    admin_client: TestClient,
    conference: dict,
    sections: list[dict],
    participant_factory: Callable[[str, str], TestClient],
) -> None:
    """Выборка броней фильтруется на сервере: чужие брони участнику не видны."""
    mine = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    my_booking = client.post("/api/v1/hotel-bookings", json=_hotel_payload(mine)).json()

    foreign = participant_factory("Второй Гость", "second-hotel@example.com")
    foreign_application = _accepted_application(
        foreign, admin_client, conference, sections, section_index=1, needs_hotel=True
    )
    foreign_booking = foreign.post("/api/v1/hotel-bookings", json=_hotel_payload(foreign_application)).json()

    listed = client.get("/api/v1/hotel-bookings?limit=200").json()["items"]
    listed_ids = {item["id"] for item in listed}
    assert my_booking["id"] in listed_ids
    # Чужая бронь в выборку участника не попадает.
    assert foreign_booking["id"] not in listed_ids
    assert client.get(f"/api/v1/hotel-bookings/{foreign_booking['id']}").status_code == 403

    # Администратор видит брони всех участников.
    admin_ids = {item["id"] for item in admin_client.get("/api/v1/hotel-bookings?limit=200").json()["items"]}
    assert {my_booking["id"], foreign_booking["id"]} <= admin_ids


def test_expire_stale_bookings_endpoint(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Служебная операция пометки просроченных броней доступна только администратору."""
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    client.post("/api/v1/hotel-bookings", json=_hotel_payload(application))

    denied = client.post("/api/v1/hotel-bookings/expire-stale")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "admin_only"

    # Свежая бронь не должна истечь.
    assert admin_client.post("/api/v1/hotel-bookings/expire-stale").json()["expired"] == 0


def test_reject_hotel_booking(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Администратор может не только подтвердить, но и отклонить запрос участника."""
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    booking = client.post("/api/v1/hotel-bookings", json=_hotel_payload(application)).json()

    denied = client.post(f"/api/v1/hotel-bookings/{booking['id']}/reject", json={"reason": "Нет мест"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "admin_only"

    rejected = admin_client.post(
        f"/api/v1/hotel-bookings/{booking['id']}/reject", json={"reason": "Нет мест"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "cancelled"
    assert "Отказ: Нет мест" in rejected.json()["comment"]

    again = admin_client.post(f"/api/v1/hotel-bookings/{booking['id']}/reject", json={"reason": "Повторно"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "hotel_already_cancelled"


def test_reject_confirmed_hotel_booking(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    """Уже подтверждённую бронь повторно не отклоняют."""
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    booking = client.post("/api/v1/hotel-bookings", json=_hotel_payload(application)).json()
    assert admin_client.post(f"/api/v1/hotel-bookings/{booking['id']}/confirm").status_code == 200

    response = admin_client.post(f"/api/v1/hotel-bookings/{booking['id']}/reject", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "hotel_already_confirmed"


def test_reject_expired_hotel_booking(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict], db
) -> None:  # noqa: ANN001
    """Истёкшую бронь отклонить нельзя: её сначала помечает служебная операция."""
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    booking = client.post("/api/v1/hotel-bookings", json=_hotel_payload(application)).json()

    stale = db.get(models.HotelBooking, booking["id"])
    stale.confirmation_deadline = models.utcnow() - timedelta(hours=1)
    db.commit()

    assert admin_client.post("/api/v1/hotel-bookings/expire-stale").json()["expired"] == 1
    assert client.get(f"/api/v1/hotel-bookings/{booking['id']}").json()["status"] == "expired"

    response = admin_client.post(f"/api/v1/hotel-bookings/{booking['id']}/reject", json={"reason": "Поздно"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "hotel_not_rejectable"


def test_withdraw_cancels_hotel_booking(
    client: TestClient, admin_client: TestClient, conference: dict, sections: list[dict]
) -> None:
    application = _accepted_application(client, admin_client, conference, sections, needs_hotel=True)
    booking = client.post("/api/v1/hotel-bookings", json=_hotel_payload(application)).json()
    client.post(f"/api/v1/applications/{application['id']}/withdraw")
    assert client.get(f"/api/v1/hotel-bookings/{booking['id']}").json()["status"] == "cancelled"
