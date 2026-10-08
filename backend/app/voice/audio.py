from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import (
    TTS_API_KEY,
    TTS_API_URL,
    TTS_PROVIDER,
    TTS_VOICE_EN,
    TTS_VOICE_TA,
    VOICE_AUDIO_DIR,
    VOICE_AUDIO_PUBLIC_URL,
)

logger = logging.getLogger(__name__)


def _cache_path(text: str, lang: str) -> Path:
    voice = TTS_VOICE_TA if lang == "ta" else TTS_VOICE_EN
    digest = hashlib.sha256(f"{text}|{lang}|{voice}".encode()).hexdigest()
    return VOICE_AUDIO_DIR / f"{digest}.mp3"


def audio_url(text: str, lang: str) -> str | None:
    """Return a cached MP3 URL, synthesizing only on an explicit provider miss."""
    if not TTS_PROVIDER or not VOICE_AUDIO_PUBLIC_URL:
        return None
    path = _cache_path(text, lang)
    if not path.exists():
        if not _synthesize(text, lang, path):
            return None
    return f"{VOICE_AUDIO_PUBLIC_URL.rstrip('/')}/{quote(path.name)}"


def prewarm_fixed_audio() -> int:
    """Cache fixed phrase audio when a TTS provider and public URL are configured."""
    if not TTS_PROVIDER or not VOICE_AUDIO_PUBLIC_URL:
        return 0
    import json
    phrases_path = Path(__file__).with_name("phrases.json")
    phrases = json.loads(phrases_path.read_text(encoding="utf-8"))
    warmed = 0
    for lang, values in phrases.items():
        for text in values.values():
            if "{" not in text and audio_url(text, lang):
                warmed += 1
    return warmed


def _synthesize(text: str, lang: str, path: Path) -> bool:
    if not TTS_API_URL:
        return False
    try:
        voice = TTS_VOICE_TA if lang == "ta" else TTS_VOICE_EN
        response = httpx.post(
            TTS_API_URL,
            json={"text": text, "lang": lang, "voice": voice},
            headers={"Authorization": f"Bearer {TTS_API_KEY}"} if TTS_API_KEY else {},
            timeout=5.0,
        )
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return True
    except Exception as exc:
        logger.warning("TTS synthesis failed; falling back to Twilio Say: %s", exc)
        return False
