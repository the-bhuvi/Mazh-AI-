#!/usr/bin/env python3
"""Asterisk AGI bridge for the authenticated Mazh AI phone API."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from hashlib import sha1
from pathlib import Path
from urllib import error, request

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
WHITESPACE_RE = re.compile(r"\s+")
MAX_SPOKEN_TEXT_LEN = 360
REQUEST_TIMEOUT_SECONDS = 8
DEFAULT_TTS_CACHE_DIR = "/usr/share/asterisk/sounds/en/mazh/generated"
DEFAULT_PIPER_MODEL = "/opt/piper/voices/en_GB-cori-medium.onnx"
TTS_TIMEOUT_SECONDS = 120


def agi(command: str) -> str:
    print(command, flush=True)
    response = sys.stdin.readline()
    if not response:
        raise RuntimeError("No AGI response received from Asterisk.")
    return response.strip()


def _quote_agi_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def set_var(name: str, value: str) -> None:
    reply = agi(f"SET VARIABLE {name} {_quote_agi_value(value)}")
    if not reply.startswith("200 result=1"):
        raise RuntimeError(f"Failed to set AGI variable {name}: {reply}")


def _normalize_text(text: str) -> str:
    cleaned = CONTROL_CHARS_RE.sub(" ", str(text))
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
    if len(cleaned) > MAX_SPOKEN_TEXT_LEN:
        cleaned = cleaned[: MAX_SPOKEN_TEXT_LEN - 1].rstrip() + "."
    return cleaned or "No weather message available."


def _tts_commands(text: str, wav_path: Path) -> list[list[str]]:
    """Ordered candidate TTS commands; piper reads text on stdin, espeak takes it as an argument."""
    commands: list[list[str]] = []
    model = os.environ.get("MAZH_TTS_MODEL", DEFAULT_PIPER_MODEL)
    piper_bin = shutil.which("piper") or ("/opt/piper/piper" if os.access("/opt/piper/piper", os.X_OK) else None)
    if piper_bin and model and Path(model).is_file():
        # Flag spelling differs across piper releases; try both.
        for flag in ("--output-file", "--output_file"):
            commands.append([piper_bin, "--model", model, flag, str(wav_path)])
    voice = os.environ.get("MAZH_TTS_VOICE", "en")
    speed = os.environ.get("MAZH_TTS_SPEED", "145")
    if shutil.which("espeak-ng"):
        commands.append(["espeak-ng", "-v", voice, "-s", speed, "-w", str(wav_path), text])
    if shutil.which("espeak"):
        commands.append(["espeak", "-v", voice, "-s", speed, "-w", str(wav_path), text])
    return commands


def _convert_wav_for_asterisk(source_wav: Path, target_wav: Path) -> None:
    if shutil.which("sox"):
        # Telephony tuning: band-limit like a phone channel and normalize
        # level (ulaw loses clarity on quiet audio).
        subprocess.run(
            ["sox", str(source_wav), "-r", "8000", "-c", "1", "-b", "16", "-e", "signed-integer",
             str(target_wav), "highpass", "80", "lowpass", "3400", "gain", "-n", "-1.5"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    if shutil.which("ffmpeg"):
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source_wav), "-ar", "8000", "-ac", "1", str(target_wav)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    shutil.move(str(source_wav), str(target_wav))


def _synthesize_tts(text: str) -> str:
    cache_dir = Path(os.environ.get("MAZH_TTS_CACHE_DIR", DEFAULT_TTS_CACHE_DIR)).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    digest = sha1(text.encode("utf-8")).hexdigest()[:16]
    target_wav = cache_dir / f"wx-{digest}.wav"
    if target_wav.exists():
        return target_wav.stem

    with tempfile.TemporaryDirectory(prefix="mazh-tts-") as temp_dir:
        source_wav = Path(temp_dir) / "speech.wav"
        commands = _tts_commands(text, source_wav)
        if not commands:
            return ""
        for cmd in commands:
            try:
                subprocess.run(
                    cmd,
                    input=text.encode("utf-8") if cmd[0].endswith("piper") else None,
                    check=True,
                    timeout=TTS_TIMEOUT_SECONDS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if source_wav.exists() and source_wav.stat().st_size > 44:
                    break
            except (subprocess.SubprocessError, OSError):
                source_wav.unlink(missing_ok=True)
                continue
        else:
            return ""
        converted = Path(temp_dir) / "speech-asterisk.wav"
        _convert_wav_for_asterisk(source_wav, converted)
        staged = cache_dir / f".{target_wav.name}.tmp"
        shutil.move(str(converted), str(staged))
        os.replace(staged, target_wav)
        target_wav.chmod(0o644)
    return target_wav.stem


def _audio_var_name_for_dialplan(stem_name: str) -> str:
    # Playback() expects a path relative to the sounds root without extension.
    return f"mazh/generated/{stem_name}"


def _load_env_file(path: str) -> None:
    """Fallback env source: the Asterisk service env may lack MAZH_API_URL.

    systemd EnvironmentFile is not always applied to a long-running service
    (unit edited after start), so read the file directly if vars are missing.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key.isidentifier() and not os.environ.get(key):
                    os.environ[key] = value
    except OSError:
        pass


PIN_FALLBACK_RE = re.compile(r"^PIN \d+ \((.+)\)$")
GEO_CACHE_DIR = Path(os.environ.get("MAZH_TTS_CACHE_DIR", DEFAULT_TTS_CACHE_DIR)) / "geonames"


def _reverse_geocode_name(lat: object, lon: object) -> str:
    """Resolve coordinates to a place name via Nominatim (cached on disk)."""
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return ""
    try:
        GEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = GEO_CACHE_DIR / f"geo-{float(lat):.5f}-{float(lon):.5f}.json"
    except OSError:
        cache_file = None
    if cache_file and cache_file.exists():
        try:
            name = json.loads(cache_file.read_text(encoding="utf-8")).get("name", "")
            if name:
                return str(name)
        except (OSError, ValueError):
            pass
    url = (
        "https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=14"
        f"&lat={lat}&lon={lon}"
    )
    req = request.Request(url, headers={"User-Agent": "MazhAI-IVR/1.0 (weather IVR)"})
    try:
        with request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, TimeoutError, ValueError, OSError):
        return ""
    addr = data.get("address") or {}
    # Prefer the district name alone; tiny locality names are hard to place.
    name = str(addr.get("state_district") or addr.get("county") or "")
    if not name:
        for key in ("city", "town", "village", "suburb", "neighbourhood"):
            if addr.get(key):
                name = str(addr[key])
                break
    if not name:
        name = str(data.get("name", "") or "")
    if name and cache_file:
        try:
            cache_file.write_text(json.dumps({"name": name}), encoding="utf-8")
        except OSError:
            pass
    return name


def _spoken_message(result: dict, pin: str) -> str:
    """Compose spoken text: lead with a clean place name, then the report.

    Backend names can be 'PIN 682001 (Fort Kochi)' (Nominatim fallback) or long
    compounds like 'X / Y, District'; clean them so TTS sounds natural. When the
    backend only knows the code itself (e.g. 'PIN 601204 (601204)'), reverse-
    geocode the coordinates to a real place name.
    """
    location = result.get("location") or {}
    original_name = str(location.get("name", "") or "")
    message = str(result.get("message", "") or "")

    name = original_name
    match = PIN_FALLBACK_RE.match(name)
    if match:
        name = match.group(1)
    if " / " in name:
        name = name.split(" / ")[-1].strip()
    if name.endswith(f"PIN {pin}"):
        name = name[: -len(f"PIN {pin}")].rstrip(" ,()")

    if not name or name.isdigit() or name == pin:
        resolved = _reverse_geocode_name(location.get("lat"), location.get("lon"))
        if resolved:
            name = resolved

    if original_name and name and original_name != name:
        message = message.replace(original_name, name)
    if name and message.startswith(name):
        message = message[len(name):].lstrip(" .:,")

    return f"{name}. {message}".strip() if name else message


def main() -> None:
    for line in sys.stdin:
        if line == "\n":
            break

    set_var("MAZH_OK", "0")
    set_var("MAZH_HAS_AUDIO", "0")
    set_var("MAZH_AUDIO_FILE", "")
    set_var("MAZH_NOTFOUND", "0")
    set_var("MAZH_MESSAGE", "The weather service is temporarily unavailable.")

    _load_env_file(os.environ.get("MAZH_ENV_FILE", "/etc/asterisk/mazh.env"))

    mode = sys.argv[1] if len(sys.argv) > 1 else "weather"
    pin = sys.argv[2] if len(sys.argv) > 2 else ""
    phone = sys.argv[3] if len(sys.argv) > 3 else ""
    if not pin.isdigit() or len(pin) != 6:
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
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        if exc.code == 400:
            # Backend rejects unresolvable PINs as 400; let the caller retry.
            set_var("MAZH_OK", "0")
            set_var("MAZH_NOTFOUND", "1")
            set_var("MAZH_MESSAGE", "Sorry, we could not find weather for that postal code.")
            return
        set_var("MAZH_OK", "0")
        set_var("MAZH_MESSAGE", "The weather service is temporarily unavailable.")
        return
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        set_var("MAZH_OK", "0")
        set_var("MAZH_MESSAGE", "The weather service is temporarily unavailable.")
        return

    message = _normalize_text(_spoken_message(result, pin))
    is_success = bool(result.get("success", False))
    set_var("MAZH_OK", "1" if is_success else "0")
    set_var("MAZH_MESSAGE", message)
    if not is_success or mode == "sms":
        return

    try:
        stem = _synthesize_tts(message)
    except (subprocess.SubprocessError, OSError):
        stem = ""
    if stem:
        set_var("MAZH_AUDIO_FILE", _audio_var_name_for_dialplan(stem))
        set_var("MAZH_HAS_AUDIO", "1")


if __name__ == "__main__":
    main()
