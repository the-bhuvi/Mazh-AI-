from __future__ import annotations

import html
from typing import Iterable

from app.config import TTS_VOICE_EN, TTS_VOICE_TA
from app.voice.audio import audio_url


def _xml_text(text: str) -> str:
    return html.escape(text, quote=False)


def _speak(text: str, lang: str) -> str:
    url = audio_url(text, lang)
    if url:
        return f'<Play>{html.escape(url)}</Play>'
    voice = TTS_VOICE_TA if lang == "ta" else TTS_VOICE_EN
    language = "ta-IN" if lang == "ta" else "en-IN"
    return f'<Say voice="Polly.Aditi" language="{language}">{_xml_text(text)}</Say>'


def gather(prompt: str, action: str, lang: str, num_digits: int = 1, timeout: int = 5) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Gather input="dtmf" action="{html.escape(action, quote=True)}" method="POST" '
        f'numDigits="{num_digits}" finishOnKey="#" timeout="{timeout}">'
        f"{_speak(prompt, lang)}</Gather></Response>"
    )


def speak_then_gather(messages: Iterable[str], prompt: str, action: str, lang: str, num_digits: int = 1) -> str:
    speech = "".join(_speak(item, lang) for item in messages)
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f"{speech}<Gather input=\"dtmf\" action=\"{html.escape(action, quote=True)}\" "
        f"method=\"POST\" numDigits=\"{num_digits}\" finishOnKey=\"#\" timeout=\"5\">"
        f"{_speak(prompt, lang)}</Gather></Response>"
    )


def say_and_menu(messages: Iterable[str], menu_prompt: str, action: str, lang: str) -> str:
    return speak_then_gather(messages, menu_prompt, action, lang, 1)


def goodbye(message: str, lang: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{_speak(message, lang)}<Hangup/></Response>'
