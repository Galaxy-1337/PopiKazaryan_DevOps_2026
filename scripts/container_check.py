"""Container check: verify /health of a running container.

Console output is ASCII-only: Windows consoles decode program output using the
system code page, so non-ASCII text would be displayed as garbage.

Run (after ``docker compose up --build -d``):
    python -m scripts.container_check
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000")
ATTEMPTS = int(os.environ.get("CONTAINER_CHECK_ATTEMPTS", "20"))


def main() -> int:
    url = f"{BASE}/health"
    last_error = ""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok":
                print(f"OK  {url} -> {payload}")
                return 0
            last_error = f"status={payload.get('status')} database={payload.get('database')}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        print(f"attempt {attempt}/{ATTEMPTS}: {last_error}")
        time.sleep(2)

    print(f"FAIL: service is not available at {url}: {last_error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
