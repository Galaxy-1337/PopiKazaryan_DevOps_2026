"""Тесты оргвзносов, приглашений, тезисов и гостиницы."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _accepted_application(
    client: TestClient, conference: dict, sections: list[dict], participant_id: int, **overrides
) -> dict:
    """Создать заявку и довести её до статуса «принята»."""
    payload = {
        "conference_id": conference["id"],
        "section_id": sections[0]["id"],
        "participant_id": participant_id,
        "topic": "Практика непрерывной доставки изменений",
        "format": "offline",
        "needs_hotel": False,
    }
    payload.update(overrides)
    application = client.post("/api/v1/applications", json=payload).json()
    client.post(f"/api/v1/applications/{application['id']}/submit")
    response = client.post(
        f"/api/v1/applications/{application['id']}/decision",
        json={"accept": True, "comment": "Принято"},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Оргвзносы
# ---------------------------------------------------------------------------
def test_fee_is_charged_automatically_on_acceptance(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Правило: при принятии заявки оргвзнос начисляется автоматически."""
    application = _accepted_application(client, conference, sections, participants[0]["id"])
    fees = client.get(f"/api/v1/fees?application_id={application['id']}").json()["items"]
    assert len(fees) == 1
    assert float(fees[0]["amount"]) == 3000.0
    assert fees[0]["status"] == "pending"


def test_fee_cannot_be_charged_for_draft(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    draft = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[0]["id"],
            "topic": "Черновик без решения",
        },
    ).json()
    response = client.post("/api/v1/fees", json={"application_id": draft["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fee_requires_accepted_application"


def test_pay_and_refund_fee(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"])
    fee = client.get(f"/api/v1/fees?application_id={application['id']}").json()["items"][0]

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


def test_refund_requires_paid_fee(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"])
    fee = client.get(f"/api/v1/fees?application_id={application['id']}").json()["items"][0]
    response = client.post(f"/api/v1/fees/{fee['id']}/refund", json={"reason": "Не оплачен"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fee_not_paid"


# ---------------------------------------------------------------------------
# Приглашения
# ---------------------------------------------------------------------------
def test_invitation_is_queued_on_acceptance(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"])
    items = client.get(f"/api/v1/invitations?participant_id={participants[0]['id']}").json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "queued"
    assert application["id"] == items[0]["application_id"]


def test_invitation_queue_report_lists_pending(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    _accepted_application(client, conference, sections, participants[0]["id"])
    queue = client.get("/api/v1/reports/invitations-queue").json()
    assert queue["total"] == 1
    assert queue["items"][0]["email"] == participants[0]["email"]


def test_send_invitation_success_and_failure(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    _accepted_application(client, conference, sections, participants[0]["id"])
    invitation = client.get("/api/v1/invitations").json()["items"][0]

    failed = client.post(f"/api/v1/invitations/{invitation['id']}/send?success=false&error=SMTP")
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["attempts"] == 1

    # Повторная отправка после ошибки разрешена (очередь рассылки).
    sent = client.post(f"/api/v1/invitations/{invitation['id']}/send?success=true")
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert sent.json()["attempts"] == 2


def test_duplicate_invitation_is_rejected(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"])
    response = client.post("/api/v1/invitations", json={"application_id": application["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invitation_exists"


# ---------------------------------------------------------------------------
# Тезисы
# ---------------------------------------------------------------------------
def test_theses_require_accepted_application(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    draft = client.post(
        "/api/v1/applications",
        json={
            "conference_id": conference["id"],
            "section_id": sections[0]["id"],
            "participant_id": participants[0]["id"],
            "topic": "Черновик для тезисов",
        },
    ).json()
    response = client.post(
        f"/api/v1/applications/{draft['id']}/theses",
        json={"title": "Тезисы", "abstract": "а" * 60},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "thesis_requires_accepted_application"


def test_thesis_review_threshold(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    """Правило: тезисы принимаются при оценке не ниже 6 баллов."""
    application = _accepted_application(client, conference, sections, participants[0]["id"])
    thesis = client.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={
            "title": "Непрерывная доставка изменений",
            "abstract": "Описание практики внедрения конвейера доставки изменений в учебном проекте.",
            "keywords": "CI/CD, DevOps",
            "file_name": "thesis.pdf",
            "file_size_kb": 120,
        },
    ).json()
    assert thesis["status"] == "submitted"

    low = client.post(
        f"/api/v1/theses/{thesis['id']}/review",
        json={"reviewer_name": "Рецензент Тестовый", "score": 4, "accepted": True},
    )
    assert low.status_code == 200
    assert low.json()["status"] == "rejected"


def test_thesis_accepted_with_good_score(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"])
    thesis = client.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={"title": "Тезисы доклада", "abstract": "б" * 80},
    ).json()
    good = client.post(
        f"/api/v1/theses/{thesis['id']}/review",
        json={"reviewer_name": "Рецензент Тестовый", "score": 9, "accepted": True},
    )
    assert good.status_code == 200
    assert good.json()["status"] == "accepted"


def test_thesis_score_is_validated(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"])
    thesis = client.post(
        f"/api/v1/applications/{application['id']}/theses",
        json={"title": "Тезисы доклада", "abstract": "в" * 80},
    ).json()
    response = client.post(
        f"/api/v1/theses/{thesis['id']}/review",
        json={"reviewer_name": "Рецензент Тестовый", "score": 11},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Гостиница
# ---------------------------------------------------------------------------
def test_hotel_booking_lifecycle(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"], needs_hotel=True)
    booking = client.post(
        "/api/v1/hotel-bookings",
        json={
            "application_id": application["id"],
            "hotel_name": "Гостиница «Семёновская»",
            "room_type": "standard",
            "guests_count": 1,
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
        },
    )
    assert booking.status_code == 201, booking.text
    body = booking.json()
    assert body["status"] == "requested"
    assert body["nights"] == 2

    confirmed = client.post(f"/api/v1/hotel-bookings/{body['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


def test_hotel_dates_must_be_within_conference(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"], needs_hotel=True)
    response = client.post(
        "/api/v1/hotel-bookings",
        json={
            "application_id": application["id"],
            "hotel_name": "Гостиница «Семёновская»",
            "check_in": "2026-05-20",
            "check_out": "2026-05-22",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "hotel_dates_out_of_conference"


def test_hotel_not_available_for_online_format(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"], format="online")
    response = client.post(
        "/api/v1/hotel-bookings",
        json={
            "application_id": application["id"],
            "hotel_name": "Гостиница «Семёновская»",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "hotel_not_allowed_for_online"


def test_second_hotel_booking_is_rejected(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"], needs_hotel=True)
    payload = {
        "application_id": application["id"],
        "hotel_name": "Гостиница «Семёновская»",
        "check_in": "2026-06-01",
        "check_out": "2026-06-03",
    }
    assert client.post("/api/v1/hotel-bookings", json=payload).status_code == 201
    duplicate = client.post("/api/v1/hotel-bookings", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "hotel_booking_exists"


def test_expire_stale_bookings_endpoint(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"], needs_hotel=True)
    client.post(
        "/api/v1/hotel-bookings",
        json={
            "application_id": application["id"],
            "hotel_name": "Гостиница «Семёновская»",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
        },
    )
    # Свежая бронь не должна истечь.
    assert client.post("/api/v1/hotel-bookings/expire-stale").json()["expired"] == 0


def test_withdraw_cancels_hotel_booking(
    client: TestClient, conference: dict, sections: list[dict], participants: list[dict]
) -> None:
    application = _accepted_application(client, conference, sections, participants[0]["id"], needs_hotel=True)
    booking = client.post(
        "/api/v1/hotel-bookings",
        json={
            "application_id": application["id"],
            "hotel_name": "Гостиница «Семёновская»",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
        },
    ).json()
    client.post(f"/api/v1/applications/{application['id']}/withdraw")
    assert client.get(f"/api/v1/hotel-bookings/{booking['id']}").json()["status"] == "cancelled"
