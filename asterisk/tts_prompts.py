#!/usr/bin/env python3
"""Generate the fixed mazh/ IVR prompt WAVs with the same TTS backend as the AGI.

Usage:
    python3 tts_prompts.py [--output-dir asterisk/sounds/mazh]

Piper is preferred (set MAZH_TTS_MODEL to a .onnx voice); espeak-ng/espeak are
fallbacks. Output is 8 kHz mono 16-bit WAV, ready for Asterisk Playback().
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

AGI_DIR = Path(__file__).resolve().parent / "agi"
sys.path.insert(0, str(AGI_DIR))

import mazh_weather  # noqa: E402

PROMPTS: dict[str, str] = {
    "welcome": "Welcome to Mazh A I weather. Please have your six digit postal PIN ready.",
    "enter-pin": "Please enter your six digit postal PIN, followed by the hash key.",
    "invalid-pin": "Sorry, that PIN was not valid. Let's try again.",
    "backend-error": "Sorry, the weather service is temporarily unavailable. Please try again later.",
    "menu": (
        "For today's weather, press 1. For tomorrow's forecast, press 2. "
        "For weather alerts, press 3. To receive an SMS, press 4. "
        "To start over, press 9. To hang up, press 0."
    ),
    "no-input": "I did not receive any input.",
    "sms-sent": "A text message is on its way.",
    "goodbye": "Thank you for calling Mazh A I weather. Goodbye.",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "sounds" / "mazh"))
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not mazh_weather._tts_commands("ok", Path("/tmp/unused.wav")):
        print("No TTS backend found (piper, espeak-ng, or espeak).", file=sys.stderr)
        return 1

    failed: list[str] = []
    for name, text in PROMPTS.items():
        with tempfile.TemporaryDirectory(prefix="mazh-prompt-") as temp_dir:
            source = Path(temp_dir) / "speech.wav"
            commands = mazh_weather._tts_commands(text, source)
            done = False
            for cmd in commands:
                try:
                    subprocess.run(
                        cmd,
                        input=text.encode("utf-8") if cmd[0].endswith("piper") else None,
                        check=True,
                        timeout=180,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if source.exists() and source.stat().st_size > 44:
                        done = True
                        break
                except Exception:
                    source.unlink(missing_ok=True)
            if not done:
                failed.append(name)
                continue
            target = out_dir / f"{name}.wav"
            mazh_weather._convert_wav_for_asterisk(source, target)
            target.chmod(0o644)
            print(f"generated {target}")

    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    os.umask(0o022)
    raise SystemExit(main())
