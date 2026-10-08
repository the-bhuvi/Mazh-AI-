from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlencode

from fastapi import Request

from app.config import ENV, TWILIO_AUTH_TOKEN


def _external_url(request: Request, form: dict[str, str]) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    path = request.url.path
    query = urlencode(sorted(form.items()))
    return f"{forwarded_proto}://{forwarded_host}{path}{('?' + query) if query else ''}"


def validate_twilio_request(request: Request, form: dict[str, str]) -> bool:
    """Validate Twilio's X-Twilio-Signature using proxy-visible URL values."""
    if not TWILIO_AUTH_TOKEN:
        # Local simulator/test mode has no Twilio secret. Production must set it.
        return ENV != "production"
    supplied = request.headers.get("x-twilio-signature", "")
    if not supplied:
        return False
    digest = hmac.new(
        TWILIO_AUTH_TOKEN.encode(),
        _external_url(request, form).encode(),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, supplied)
