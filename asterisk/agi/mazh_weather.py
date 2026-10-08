#!/usr/bin/env python3
"""Asterisk AGI bridge for the authenticated Mazh AI phone API."""

from __future__ import annotations

import json
import os
import sys
from urllib import error, request


def agi(command: str) -> None:
    print(command, flush=True)


def set_var(name: str, value: str) -> None:
    safe = value.replace("\n", " ").replace("\r", " ")
    agi(f"SET VARIABLE {name} {safe}")


def main() -> None:
    for line in sys.stdin:
        if line == "\n":
            break

    mode = sys.argv[1] if len(sys.argv) > 1 else "weather"
    pin = sys.argv[2] if len(sys.argv) > 2 else ""
    phone = sys.argv[3] if len(sys.argv) > 3 else ""
    if not pin.isdigit() or len(pin) != 6:
        set_var("MAZH_OK", "0")
        set_var("MAZH_MESSAGE", "Invalid postal PIN code.")
        return

    endpoint = {
        "weather": "weather",
        "today": "today",
        "tomorrow": "tomorrow",
        "alerts": "alerts",
        "sms": "sms",
    }.get(mode)
    base_url = os.environ.get("MAZH_API_URL", "").rstrip("/")
    api_key = os.environ.get("MAZH_PHONE_API_KEY", "")
    if not endpoint or not base_url or not api_key:
        set_var("MAZH_OK", "0")
        set_var("MAZH_MESSAGE", "The weather service is not configured.")
        return

    payload = {"pin": pin}
    if mode == "sms":
        payload["phone"] = phone
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url}/api/phone/{endpoint}",
        data=body,
        headers={"Content-Type": "application/json", "X-Phone-API-Key": api_key},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
        set_var("MAZH_OK", "1" if result.get("success", False) else "0")
        set_var("MAZH_MESSAGE", str(result.get("message", "No weather message available.")))
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        set_var("MAZH_OK", "0")
        set_var("MAZH_MESSAGE", "The weather service is temporarily unavailable.")


if __name__ == "__main__":
    main()
