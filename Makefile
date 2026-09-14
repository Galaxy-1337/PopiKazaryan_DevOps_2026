# =====================================================================
#  Единый командный интерфейс проекта «Конференция»
#  Все обязательные локальные проверки выполняются через make.
#  Под Windows без GNU make используйте: .\scripts\dev.ps1 <команда>
# =====================================================================

APP_MODULE  := app.main:app
VENV        := .venv
HOST        ?= 127.0.0.1
PORT        ?= 8000

ifeq ($(OS),Windows_NT)
  PY  := $(VENV)/Scripts/python.exe
  PIP := $(PY) -m pip
else
  PY  := $(VENV)/bin/python
  PIP := $(PY) -m pip
endif

DC := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

.DEFAULT_GOAL := help
.PHONY: help setup run test quality lint format fix migrate backup restore \
        verify up down container-check logs shell clean version

help: ## Показать список команд
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-16s %s\n", $$1, $$2}'

setup: ## Первоначальная настройка: venv, зависимости, .env
	@echo "==> Создание виртуального окружения"
	python -m venv $(VENV)
	@echo "==> Установка зависимостей"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	@if [ ! -f .env ]; then cp .env.example .env; echo "==> Создан .env из .env.example (проверьте значения)"; fi
	@echo "==> Готово. Запуск: make run"

run: ## Локальный запуск приложения (uvicorn)
	$(PY) -m uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

test: ## Автоматические тесты (pytest)
	$(PY) -m pytest -q

quality: lint ## Форматирование и статический анализ
	$(PY) -m ruff format --check .

lint: ## Статический анализ (ruff check)
	$(PY) -m ruff check .

format: ## Автоматическое форматирование кода
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .
migrate: ## Применение миграций / создание схемы БД
	$(PY) -m scripts.migrate

backup: ## Резервная копия базы данных
	$(PY) -m scripts.backup

restore: ## Восстановление базы из резервной копии (FILE=backups/...)
	$(PY) -m scripts.restore $(FILE)

verify: quality test ## Полный набор локальных проверок перед коммитом
	@echo "==> Проверка работоспособности приложения"
	$(PY) -m scripts.smoke

up: ## Запуск контейнерного окружения (app + PostgreSQL)
	$(DC) up --build -d
	@echo "==> Приложение: http://$(HOST):$(PORT)  Swagger: http://$(HOST):$(PORT)/docs"

down: ## Остановка контейнерного окружения
	$(DC) down

logs: ## Логи контейнеров
	$(DC) logs -f --tail=100

shell: ## Оболочка внутри контейнера приложения
	$(DC) exec app /bin/sh

container-check: ## Проверка работоспособности контейнера через /health
	$(PY) -m scripts.container_check

version: ## Показать версию приложения
	@$(PY) -c "from app import __version__; print(__version__)"

clean: ## Удалить кэши и виртуальное окружение
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
