"""Pre-generate fixed IVR phrase audio through the configured TTS adapter."""

import json
from pathlib import Path

from app.voice.audio import audio_url


def main() -> None:
    phrases = json.loads((Path(__file__).parents[1] / "app" / "voice" / "phrases.json").read_text(encoding="utf-8"))
    for lang, values in phrases.items():
        for text in values.values():
            if "{" not in text:
                audio_url(text, lang)


if __name__ == "__main__":
    main()
