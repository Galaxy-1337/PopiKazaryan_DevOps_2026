"""Общие фикстуры тестов.

Тесты работают на отдельной тестовой базе SQLite: каждый тест получает
чистую схему, поэтому тесты не зависят от порядка выполнения.

API полностью закрыт аутентификацией: без активной сессии не выдаётся ничего,
кроме страницы входа и служебного пробника. В системе две роли, поэтому есть
две основные фикстуры:

* ``admin_client`` — сессия администратора (все разделы и служебные страницы);
* ``client`` (он же ``participant_client``) — сессия участника: он подаёт заявки,
  пишет тезисы, оформляет гостиницу и оплачивает взносы только от своего имени.

Для проверок, где нужно несколько участников, используется фабрика
``participant_factory``: она создаёт запись реестра и учётную запись с ролью
«участник» и возвращает клиент, вошедший под ней.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

# Переменные окружения должны быть выставлены ДО импорта приложения.
# CONFERENCE_SKIP_DOTENV отключает чтение файла .env, чтобы локальные настройки
# разработчика не влияли на результаты тестов.
TEST_DB = Path("data/test_conference.db").resolve()
os.environ["CONFERENCE_SKIP_DOTENV"] = "1"
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TEST_DB.as_posix()}")
os.environ.setdefault("SEED_DEMO_DATA", "true")
os.environ.setdefault("ADMIN_EMAIL", "organizer@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Conference2026")
os.environ.setdefault("DEMO_PASSWORD", "Conference2026")
os.environ.setdefault("PARTICIPANT_EMAIL", "polzovatel@example.ru")
os.environ.setdefault("PARTICIPANT_PASSWORD", "Conference2026")
os.environ.setdefault("SECTION_CAPACITY", "3")
os.environ.setdefault("HOTEL_CONFIRMATION_HOURS", "48")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal, drop_all, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

# Пароль учётных записей, создаваемых тестами.
TEST_PASSWORD = "Conference2026"


def credentials(role: str) -> tuple[str, str]:
    """Адрес и пароль учётной записи.

    Значения берутся из настроек приложения, поэтому тесты не зависят от того,
    что записано в локальном файле ``.env``: проверяется именно то, что создаёт
    наполнение базы данных.
    """
    from app.config import get_settings

    settings = get_settings()
    accounts = {
        "admin": (settings.admin_email, settings.effective_admin_password),
        "participant": (settings.participant_email, settings.effective_participant_password),
    }
    return accounts[role]


ADMIN = credentials("admin")
PARTICIPANT = credentials("participant")


def _login(client: TestClient, credentials: tuple[str, str]) -> TestClient:
    """Выполнить вход и вернуть тот же клиент с cookie сессии."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": credentials[0], "password": credentials[1]},
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> Iterator[None]:
    """Убрать тестовую базу до и после прогона.

    Иначе в ней остаются учётные записи прошлых запусков со старым паролем, и
    вход в тестах перестаёт работать.
    """
    TEST_DB.parent.mkdir(parents=True, exist_ok=True)
    if TEST_DB.exists():
        TEST_DB.unlink()
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
def anon_client() -> Iterator[TestClient]:
    """Клиент без входа в систему — для проверки защиты маршрутов."""
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture
def admin_client() -> Iterator[TestClient]:
    """Клиент администратора: все разделы и служебные страницы."""
    with TestClient(fastapi_app) as test_client:
        yield _login(test_client, ADMIN)


@pytest.fixture
def participant_client() -> Iterator[TestClient]:
    """Клиент демонстрационного участника (учётная запись из наполнения базы)."""
    with TestClient(fastapi_app) as test_client:
        yield _login(test_client, PARTICIPANT)


@pytest.fixture
def client(participant_client: TestClient) -> TestClient:
    """Основной клиент тестов предметной области — участник.

    Заявки, тезисы, гостиницу и оплату взносов выполняет именно участник: эти
    операции администратору недоступны.
    """
    return participant_client


@pytest.fixture
def participant_factory(db: Session) -> Callable[[str, str], TestClient]:
    """Фабрика участников: запись реестра + учётная запись + клиент с сессией.

    Используется там, где проверка требует нескольких участников (например,
    правило вместимости секции): каждый участник работает от своего имени.
    """
    from app import auth, models

    def factory(full_name: str, email: str) -> TestClient:
        participant = models.Participant(
            full_name=full_name,
            email=email,
            organization="Московский Политех",
            city="Москва",
        )
        db.add(participant)
        db.flush()
        user = auth.create_user(
            db,
            email=email,
            password=TEST_PASSWORD,
            role=models.UserRole.PARTICIPANT,
            full_name=full_name,
            participant=participant,
        )
        db.add(user)
        db.commit()

        new_client = TestClient(fastapi_app)
        response = new_client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
        assert response.status_code == 200, response.text
        return new_client

    return factory


@pytest.fixture
def conference(admin_client: TestClient) -> dict:
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
    response = admin_client.post("/api/v1/conferences", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()

    for index in range(3):
        section = admin_client.post(
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
def sections(admin_client: TestClient, conference: dict) -> list[dict]:
    """Секции тестовой конференции."""
    response = admin_client.get(f"/api/v1/sections?conference_id={conference['id']}")
    assert response.status_code == 200
    return response.json()["items"]


@pytest.fixture
def participants(admin_client: TestClient) -> list[dict]:
    """Пять участников с уникальными адресами (создаёт администратор)."""
    created = []
    for index in range(5):
        response = admin_client.post(
            "/api/v1/participants",
            json={
                "full_name": f"Участник Тестовый {index + 1}",
                "email": f"user{index + 1}@example.com",
                "organization": "Московский Политех",
                "city": "Москва",
            },
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    return created
