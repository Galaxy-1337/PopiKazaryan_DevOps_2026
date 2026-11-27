"""Тесты служебных эндпоинтов и обработки некорректных запросов.

Служебные адреса приложения (``/health``, ``/version``, ``/openapi.json``)
доступны только администратору; участнику они закрыты. Для проверок контейнера
и CI есть отдельный публичный пробник ``/internal/health``: он не требует
сессии и отдаёт только признак готовности.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(admin_client: TestClient) -> None:
    """Служебный адрес проверки работоспособности отвечает и сообщает состояние БД."""
    response = admin_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == "0.1.0"


def test_version_endpoint(admin_client: TestClient) -> None:
    response = admin_client.get("/version")
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"


def test_internal_health_is_public_and_minimal(
    anon_client: TestClient, participant_client: TestClient
) -> None:
    """Пробник доступен всем и не раскрывает ни версии, ни состояния базы."""
    for client in (anon_client, participant_client):
        response = client.get("/internal/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_service_endpoints_are_admin_only(participant_client: TestClient, anon_client: TestClient) -> None:
    for path in ("/health", "/version", "/openapi.json"):
        forbidden = participant_client.get(path)
        assert forbidden.status_code == 403, f"{path}: {forbidden.status_code}"
        assert forbidden.json()["error"]["code"] == "admin_only"

        unauthorized = anon_client.get(path)
        assert unauthorized.status_code == 401, f"{path}: {unauthorized.status_code}"
        assert unauthorized.json()["error"]["code"] == "unauthorized"


def test_request_id_header_is_returned(admin_client: TestClient) -> None:
    """Каждый ответ содержит сквозной идентификатор запроса."""
    response = admin_client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_openapi_schema_is_available(admin_client: TestClient) -> None:
    response = admin_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["version"] == "0.1.0"
    assert "/api/v1/applications" in schema["paths"]


def test_web_interface_is_served(admin_client: TestClient) -> None:
    """Веб-интерфейс обязателен по заданию — проверяем отдачу страницы."""
    response = admin_client.get("/")
    assert response.status_code == 200
    assert "Конференция" in response.text
    assert "panel-applications" in response.text


def test_validation_error_has_unified_format(admin_client: TestClient) -> None:
    """Некорректный запрос возвращает 422 в едином формате ошибки."""
    response = admin_client.post("/api/v1/participants", json={"full_name": "X", "email": "не-почта"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert {item["field"] for item in error["details"]} >= {"body.email"}


def test_unknown_route_returns_404_in_unified_format(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/unknown-entity")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


def test_missing_entity_returns_404(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/conferences/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_invalid_query_parameter_returns_422(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/conferences?limit=0")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
