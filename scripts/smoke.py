"""Дымовая проверка приложения: запускает сервер и проверяет ключевые эндпоинты.

Используется в ``make verify`` и в CI, чтобы убедиться, что приложение
действительно поднимается и отвечает, а не только проходит модульные тесты.

Запуск:
    python -m scripts.smoke
"""

from __future__ import annotations

import socket
import subprocess  # noqa: S404
import sys
import time
import urllib.error
import urllib.request

HOST = "127.0.0.1"
PORT = 8137
BASE = f"http://{HOST}:{PORT}"
ENDPOINTS = ["/health", "/version", "/", "/openapi.json", "/api/v1/conferences"]


def _free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((HOST, port)) != 0


def _wait_until_ready(timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as response:  # noqa: S310
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.7)
    return False


def main() -> int:
    if not _free_port(PORT):
        print(f"Порт {PORT} занят — пропускаю дымовую проверку")
        return 0

    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    failures: list[str] = []
    try:
        if not _wait_until_ready():
            print("ОШИБКА: приложение не поднялось за отведённое время")
            return 1

        for endpoint in ENDPOINTS:
            url = f"{BASE}{endpoint}"
            try:
                with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
                    status = response.status
            except urllib.error.HTTPError as exc:
                status = exc.code
            ok = status < 400
            print(f"{'OK  ' if ok else 'FAIL'} {endpoint} -> HTTP {status}")
            if not ok:
                failures.append(endpoint)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            process.kill()

    if failures:
        print(f"Дымовая проверка не пройдена: {', '.join(failures)}")
        return 1
    print("Дымовая проверка пройдена")
    return 0


if __name__ == "__main__":
    sys.exit(main())
