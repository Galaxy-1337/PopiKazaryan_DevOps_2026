# =====================================================================
#  Единый командный интерфейс проекта «Конференция»
#
#  Все обязательные локальные проверки выполняются через make.
#  Makefile намеренно не использует Unix-утилиты (grep, awk, sed, rm,
#  find, cp): на Windows их нет, поэтому вся логика реализована
#  средствами make и Python, который и так нужен проекту.
#
#  Быстрый старт:  make help
# =====================================================================

APP_MODULE := app.main:app
VENV       := .venv
HOST       ?= 127.0.0.1
PORT       ?= 8000

# --- Интерпретатор Python: сначала виртуальное окружение, потом системный ---
ifeq ($(OS),Windows_NT)
  PYTHON := $(if $(wildcard $(VENV)/Scripts/python.exe),$(VENV)/Scripts/python.exe,python)
  # Оболочка cmd.exe корректно возвращает код выхода, в отличие от sh.exe из Git.
  SHELL  := cmd.exe
else
  PYTHON := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python)
endif

# --- docker compose: подходит и плагин, и отдельный бинарник ---
DC := $(shell docker compose version >/dev/null 2>&1 && echo docker compose || echo docker-compose)

.DEFAULT_GOAL := help
.PHONY: help setup run test quality lint format migrate backup restore \
        verify up down container-check logs shell version clean

# ---------------------------------------------------------------------
help: ## Показать список команд
	@$(PYTHON) scripts/make_help.py

setup: ## Первоначальная настройка: venv, зависимости, .env
	@echo ==^> Создание виртуального окружения
	python -m venv $(VENV)
	@echo ==^> Установка зависимостей
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements-dev.txt
	@$(PYTHON) scripts/make_setup_env.py
	@echo ==^> Готово. Запуск: make run

run: ## Локальный запуск приложения (uvicorn)
	@echo ==^> http://$(HOST):$(PORT)
	$(PYTHON) -m uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

test: ## Автоматические тесты (pytest)
	$(PYTHON) -m pytest -q

quality: lint ## Форматирование и статический анализ
	$(PYTHON) -m ruff format --check .

lint: ## Статический анализ (ruff check)
	$(PYTHON) -m ruff check .

format: ## Автоматическое форматирование кода
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

migrate: ## Применение миграций / создание схемы БД
	$(PYTHON) -m scripts.migrate

backup: ## Резервная копия базы данных
	$(PYTHON) -m scripts.backup

restore: ## Восстановление базы из копии (make restore FILE=backups/...)
	@$(PYTHON) -m scripts.restore $(FILE)

verify: ## Полный набор локальных проверок перед коммитом
	@echo ==^> 1/4 проверка форматирования
	@$(PYTHON) -m ruff format --check .
	@echo ==^> 2/4 статический анализ
	@$(PYTHON) -m ruff check .
	@echo ==^> 3/4 автоматические тесты
	@$(PYTHON) -m pytest -q
	@echo ==^> 4/4 дымовая проверка приложения
	@$(PYTHON) -m scripts.smoke
	@echo ==^> Все локальные проверки пройдены

up: ## Запуск контейнерного окружения (app + PostgreSQL)
	$(DC) up --build -d
	@echo ==^> Приложение: http://$(HOST):$(PORT)  Swagger: http://$(HOST):$(PORT)/docs

down: ## Остановка контейнерного окружения
	$(DC) down

logs: ## Логи контейнеров
	$(DC) logs -f --tail=100

shell: ## Оболочка внутри контейнера приложения
	$(DC) exec app /bin/sh

container-check: ## Проверка работоспособности контейнера через /health
	$(PYTHON) -m scripts.container_check

version: ## Показать версию приложения
	@$(PYTHON) -c "from app import __version__; print(__version__)"

clean: ## Удалить кэши и виртуальное окружение
	@$(PYTHON) scripts/make_clean.py
