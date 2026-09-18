"""Smoke check: start the application and verify key endpoints.

The application requires authentication, so the check does three passes:

* public endpoints must answer without a session;
* protected endpoints must answer 401 without a session;
* after login the protected endpoints must answer 200.

Environment variables ``SMOKE_EMAIL`` and ``SMOKE_PASSWORD`` override the
credentials used for the authenticated pass (defaults follow demo accounts).

Console output is ASCII-only: Windows consoles decode program output using the
system code page, so non-ASCII text would be displayed as garbage.

Run:
    python -m scripts.smoke
"""

from __future__ import annotations

import json
import os
import socket
import subprocess  # noqa: S404
import sys
import time
import urllib.error
import urllib.request

HOST = "127.0.0.1"
PORT = 8137
BASE = f"http://{HOST}:{PORT}"

# Endpoints that stay open without a session.
PUBLIC_ENDPOINTS = ["/health", "/version", "/api/v1/auth/roles", "/login", "/openapi.json"]

# Endpoints protected by authentication: 401 is expected without a session.
PROTECTED_ENDPOINTS = ["/api/v1/conferences", "/api/v1/applications", "/api/v1/auth/me"]

# Endpoints checked after signing in as the organizer.
AUTHENTICATED_ENDPOINTS = ["/api/v1/conferences", "/api/v1/sections", "/api/v1/auth/me"]

EMAIL = os.environ.get("SMOKE_EMAIL", "organizer@example.com")
PASSWORD = os.environ.get("SMOKE_PASSWORD", "Conference2026")


def _request(path: str, *, cookie: str | None = None, payload: dict | None = None) -> tuple[int, str]:
    """Perform a request and return the status code and the Set-Cookie header."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(  # noqa: S310 — адрес формируется внутри скрипта
        f"{BASE}{path}", data=data, method="POST" if data else "GET"
    )
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310  # nosec B310
            return response.status, response.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Set-Cookie", "")


def _free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((HOST, port)) != 0


def _wait_until_ready(timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = _request("/health")
            if status == 200:
                return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.7)
    return False


def main() -> int:
    if not _free_port(PORT):
        print(f"Port {PORT} is busy - skipping the smoke check")
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
            print("FAIL: the application did not start within the time limit")
            return 1

        # 1. Open addresses
        for endpoint in PUBLIC_ENDPOINTS:
            status, _ = _request(endpoint)
            ok = status < 400
            print(f"{'OK  ' if ok else 'FAIL'} {endpoint} (public) -> HTTP {status}")
            if not ok:
                failures.append(endpoint)

        # 2. Protected addresses without a session
        for endpoint in PROTECTED_ENDPOINTS:
            status, _ = _request(endpoint)
            ok = status == 401
            print(f"{'OK  ' if ok else 'FAIL'} {endpoint} (no session) -> HTTP {status} (expected 401)")
            if not ok:
                failures.append(endpoint)

        # 3. Sign in and repeat the protected addresses with the session
        status, set_cookie = _request("/api/v1/auth/login", payload={"email": EMAIL, "password": PASSWORD})
        if status != 200:
            print(f"FAIL /api/v1/auth/login -> HTTP {status} (check SMOKE_EMAIL / SMOKE_PASSWORD)")
            failures.append("/api/v1/auth/login")
        else:
            print(f"OK   /api/v1/auth/login -> HTTP {status}")
            cookie = set_cookie.split(";")[0]
            for endpoint in AUTHENTICATED_ENDPOINTS:
                endpoint_status, _ = _request(endpoint, cookie=cookie)
                ok = endpoint_status == 200
                print(f"{'OK  ' if ok else 'FAIL'} {endpoint} (session) -> HTTP {endpoint_status}")
                if not ok:
                    failures.append(endpoint)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            process.kill()

    if failures:
        print(f"Smoke check failed: {', '.join(failures)}")
        return 1
    print("Smoke check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
