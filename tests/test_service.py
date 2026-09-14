"""Тесты служебных эндпоинтов и обработки некорректных запросов."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """Служебный адрес проверки работоспособности отвечает и сообщает состояние БД."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == "0.1.0"


def test_version_endpoint(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"


def test_request_id_header_is_returned(client: TestClient) -> None:
    """Каждый ответ содержит сквозной идентификатор запроса."""
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_openapi_schema_is_available(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["version"] == "0.1.0"
    assert "/api/v1/applications" in schema["paths"]


def test_web_interface_is_served(client: TestClient) -> None:
    """Веб-интерфейс обязателен по заданию — проверяем отдачу страницы."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Конференция" in response.text
    assert "panel-applications" in response.text


def test_validation_error_has_unified_format(client: TestClient) -> None:
    """Некорректный запрос возвращает 422 в едином формате ошибки."""
    response = client.post("/api/v1/participants", json={"full_name": "X", "email": "не-почта"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert {item["field"] for item in error["details"]} >= {"body.email"}


def test_unknown_route_returns_404_in_unified_format(client: TestClient) -> None:
    response = client.get("/api/v1/unknown-entity")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


def test_missing_entity_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/conferences/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_invalid_query_parameter_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/conferences?limit=0")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
