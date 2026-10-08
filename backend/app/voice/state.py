from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode

from app.config import VOICE_BASE_URL, VOICE_STATE_SECRET


class InvalidVoiceToken(ValueError):
    pass


def encode_state(state: dict[str, Any], ttl_seconds: int = 1800) -> str:
    payload = {**state, "exp": int(time.time()) + ttl_seconds}
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    signature = hmac.new(
        VOICE_STATE_SECRET.encode(), encoded.encode(), hashlib.sha256
    ).digest()
    return f"{encoded}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def decode_state(token: str | None) -> dict[str, Any]:
    if not token or "." not in token:
        raise InvalidVoiceToken("Missing voice state")
    encoded, signature_text = token.split(".", 1)
    expected = hmac.new(
        VOICE_STATE_SECRET.encode(), encoded.encode(), hashlib.sha256
    ).digest()
    try:
        supplied = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidVoiceToken("Malformed voice state") from exc
    if not hmac.compare_digest(expected, supplied):
        raise InvalidVoiceToken("Invalid voice state signature")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise InvalidVoiceToken("Expired voice state")
    return payload


def action_url(path: str, state: dict[str, Any]) -> str:
    token = encode_state(state)
    query = urlencode({"s": token})
    base = VOICE_BASE_URL.rstrip("/")
    return f"{base}{path}?{query}" if base else f"{path}?{query}"


def advance_idle(state: dict[str, Any]) -> dict[str, Any]:
    next_state = dict(state)
    next_state["idle_count"] = int(state.get("idle_count", 0)) + 1
    return next_state
