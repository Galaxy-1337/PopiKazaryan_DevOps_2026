"""Smoke check: start the application and verify the access rules.

The application is closed by default: without an active session nothing is served
except the login page, its static files and the service probe. The check does four
passes:

* public addresses answer without a session (``/login``, ``/internal/health``);
* every other address is closed without a session (401 for the API, a redirect to
  the login page for browser pages, including ``/docs``, ``/redoc`` and
  ``/openapi.json``);
* the administrator reaches every section and the service pages;
* the participant reaches only their own sections, while the service pages and the
  registry of participants stay closed even after signing in.

Environment variables ``SMOKE_EMAIL`` / ``SMOKE_PASSWORD`` and
``SMOKE_PARTICIPANT_EMAIL`` / ``SMOKE_PARTICIPANT_PASSWORD`` override the
credentials used for the authenticated passes.

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

# Addresses that stay open without a session.
PUBLIC_ENDPOINTS = ["/login", "/internal/health"]

# Browser pages: without a session they redirect to the login page.
REDIRECTED_ENDPOINTS = ["/", "/docs", "/redoc"]

# API addresses: without a session they answer 401.
CLOSED_API_ENDPOINTS = [
    "/health",
    "/version",
    "/openapi.json",
    "/api/v1/auth/me",
    "/api/v1/auth/roles",
    "/api/v1/conferences",
    "/api/v1/sections",
    "/api/v1/participants",
    "/api/v1/applications",
    "/api/v1/fees",
    "/api/v1/invitations",
    "/api/v1/theses",
    "/api/v1/hotel-bookings",
    "/api/v1/reports/conference/1",
]

# Sections the administrator must reach after signing in.
ADMIN_ENDPOINTS = [
    "/api/v1/auth/me",
    "/api/v1/conferences",
    "/api/v1/sections",
    "/api/v1/participants",
    "/api/v1/applications",
    "/api/v1/fees",
    "/api/v1/invitations",
    "/api/v1/theses",
    "/api/v1/hotel-bookings",
    "/api/v1/auth/roles",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
]

# Sections the participant must reach after signing in.
PARTICIPANT_ENDPOINTS = [
    "/api/v1/auth/me",
    "/api/v1/conferences",
    "/api/v1/sections",
    "/api/v1/applications",
    "/api/v1/fees",
    "/api/v1/theses",
    "/api/v1/hotel-bookings",
]

# Addresses closed to the participant even with an active session.
PARTICIPANT_DENIED_ENDPOINTS = [
    "/api/v1/participants",
    "/api/v1/invitations",
    "/api/v1/auth/roles",
    "/api/v1/reports/conference/1",
    "/health",
    "/openapi.json",
]

ADMIN_EMAIL = os.environ.get("SMOKE_EMAIL", "organizer@example.com")
ADMIN_PASSWORD = os.environ.get("SMOKE_PASSWORD", "Conference2026")
PARTICIPANT_EMAIL = os.environ.get("SMOKE_PARTICIPANT_EMAIL", "polzovatel@example.ru")
PARTICIPANT_PASSWORD = os.environ.get("SMOKE_PARTICIPANT_PASSWORD", "Conference2026")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Не следовать перенаправлениям: ответ 303 нужно увидеть как есть."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ARG002
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _request(
    path: str,
    *,
    cookie: str | None = None,
    payload: dict | None = None,
    redirects: bool = False,
) -> tuple[int, str]:
    """Perform a request and return the status code and the Set-Cookie header."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(  # noqa: S310 — адрес формируется внутри скрипта
        f"{BASE}{path}", data=data, method="POST" if data else "GET"
    )
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if cookie:
        request.add_header("Cookie", cookie)
    opener = urllib.request.urlopen if redirects else _opener.open
    try:
        with opener(request, timeout=10) as response:  # type: ignore[operator]
            return response.status, response.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Set-Cookie", "")


def _get_json(path: str, cookie: str | None = None) -> tuple[int, dict]:
    """GET-запрос с разбором JSON-ответа (для проверок содержимого)."""
    request = urllib.request.Request(f"{BASE}{path}")  # noqa: S310 — адрес формируется внутри
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except json.JSONDecodeError:
        return 200, {}


def _login(email: str, password: str, failures: list[str]) -> str:
    """Sign in and return the session cookie (empty string on failure)."""
    status, set_cookie = _request("/api/v1/auth/login", payload={"email": email, "password": password})
    if status != 200:
        print(f"FAIL /api/v1/auth/login ({email}) -> HTTP {status}")
        failures.append(f"/api/v1/auth/login ({email})")
        return ""
    print(f"OK   /api/v1/auth/login ({email}) -> HTTP {status}")
    return set_cookie.split(";")[0]


def _check(cookie: str | None, path: str, expected: int, note: str, failures: list[str]) -> None:
    status, _ = _request(path, cookie=cookie)
    ok = status == expected
    print(f"{'OK  ' if ok else 'FAIL'} {path} {note} -> HTTP {status} (expected {expected})")
    if not ok:
        failures.append(f"{path}{note}")


def _free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((HOST, port)) != 0


def _wait_until_ready(timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = _request("/internal/health", redirects=True)
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
            _check(None, endpoint, 200, "(public)", failures)

        # 2. Closed without a session
        for endpoint in REDIRECTED_ENDPOINTS:
            _check(None, endpoint, 303, "(no session)", failures)
        for endpoint in CLOSED_API_ENDPOINTS:
            _check(None, endpoint, 401, "(no session)", failures)

        # 3. Administrator
        admin_cookie = _login(ADMIN_EMAIL, ADMIN_PASSWORD, failures)
        if admin_cookie:
            for endpoint in ADMIN_ENDPOINTS:
                _check(admin_cookie, endpoint, 200, "(admin)", failures)

        # 4. Participant
        participant_cookie = _login(PARTICIPANT_EMAIL, PARTICIPANT_PASSWORD, failures)
        if participant_cookie:
            for endpoint in PARTICIPANT_ENDPOINTS:
                _check(participant_cookie, endpoint, 200, "(participant)", failures)
            for endpoint in PARTICIPANT_DENIED_ENDPOINTS:
                _check(participant_cookie, endpoint, 403, "(participant, denied)", failures)

            # Участник не должен видеть заявки, поданные из другой учётной записи.
            # Учётная запись участника универсальная, поэтому «свои» заявки
            # определяются по владельцу (created_by_user_id), а не по участнику.
            me_status, me = _get_json("/api/v1/auth/me", participant_cookie)
            own_user_id = me.get("id") if me_status == 200 else None
            list_status, page = _get_json("/api/v1/applications?limit=200", participant_cookie)
            foreign = [
                item["id"] for item in page.get("items", []) if item.get("created_by_user_id") != own_user_id
            ]
            if own_user_id is None:
                print("FAIL participant session is not recognised")
                failures.append("participant profile")
            elif foreign:
                print(f"FAIL participant sees foreign applications: {foreign}")
                failures.append("applications scoping")
            else:
                print(f"OK   participant sees only own applications ({page.get('total', 0)} found)")

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
