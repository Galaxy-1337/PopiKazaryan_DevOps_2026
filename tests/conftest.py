"""Общие фикстуры тестов.

Тесты работают на отдельной тестовой базе SQLite: каждый тест получает
чистую схему, поэтому тесты не зависят от порядка выполнения.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Переменные окружения должны быть выставлены ДО импорта приложения.
TEST_DB = Path("data/test_conference.db").resolve()
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TEST_DB.as_posix()}")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.local")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("SECTION_CAPACITY", "3")
os.environ.setdefault("HOTEL_CONFIRMATION_HOURS", "48")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal, drop_all, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> Iterator[None]:
    """Создать каталог данных и убрать файл тестовой БД после прогона."""
    TEST_DB.parent.mkdir(parents=True, exist_ok=True)
    yield
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture(autouse=True)
def clean_schema() -> Iterator[None]:
    """Пустая схема перед каждым тестом."""
    drop_all()
    from app.database import create_all

    create_all()
    from app.seed import seed_database

    seed_database()
    yield
    drop_all()


@pytest.fixture
def db() -> Iterator[Session]:
    """Сессия БД для подготовки данных в тесте."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """HTTP-клиент, работающий с приложением в одном процессе."""
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture
def conference(client: TestClient) -> dict:
    """Активная конференция с тремя секциями."""
    payload = {
        "title": "Тестовая конференция",
        "slug": "test-conf",
        "description": "Конференция для автоматических тестов",
        "starts_on": "2026-06-01",
        "ends_on": "2026-06-03",
        "location": "Москва",
        "fee_amount": "3000.00",
        "is_active": True,
    }
    response = client.post("/api/v1/conferences", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()

    for index in range(3):
        section = client.post(
            "/api/v1/sections",
            json={
                "conference_id": body["id"],
                "title": f"Секция {index + 1}",
                "capacity": 3,
            },
        )
        assert section.status_code == 201, section.text

    return body


@pytest.fixture
def sections(client: TestClient, conference: dict) -> list[dict]:
    """Секции тестовой конференции."""
    response = client.get(f"/api/v1/sections?conference_id={conference['id']}")
    assert response.status_code == 200
    return response.json()["items"]


@pytest.fixture
def participants(client: TestClient) -> list[dict]:
    """Пять участников с уникальными адресами."""
    created = []
    for index in range(5):
        response = client.post(
            "/api/v1/participants",
            json={
                "full_name": f"Участник Тестовый {index + 1}",
                "email": f"user{index + 1}@example.com",
                "organization": "Московский Политех",
                "city": "Москва",
                "role": "speaker",
            },
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    return created
