# ---------------------------------------------------------------------
# Образ приложения «Конференция».
# Многостадийная сборка: зависимости ставятся в отдельном слое,
# контейнер запускается от непривилегированного пользователя.
# ---------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# --- Слой зависимостей (кэшируется отдельно от кода) ------------------
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# --- Код приложения ---------------------------------------------------
COPY app ./app
COPY scripts ./scripts

# --- Непривилегированный пользователь --------------------------------
RUN useradd --create-home --uid 1001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

ENV APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    DATABASE_URL=sqlite+pysqlite:///./data/conference.db

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
