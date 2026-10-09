# Mazh AI Asterisk IVR

This directory contains the phone-provider configuration for a Linux Asterisk
server. Asterisk handles the call and DTMF; the FastAPI backend handles PIN
lookup, weather, ML, and deterministic voice text.

## Install

Install Asterisk with the `app_read`, `app_playback`, `app_dial`, `app_hangup`,
`app_goto`, `app_verbose`, and `res_agi` modules. Copy:

- `extensions.conf` into the active dialplan
- `agi/mazh_weather.py` into the Asterisk AGI directory (check
  `core show settings` → "AGI Scripts directory"; on this Debian install
  it is `/usr/share/asterisk/agi-bin/`, not `/var/lib/asterisk/agi-bin/`)
- `sounds/mazh/` recordings into the Asterisk sounds directory
  (`/usr/share/asterisk/sounds/en/mazh/`)

The SIP provider must route the incoming number to extension `s`.

Set `MAZH_API_URL` and `MAZH_PHONE_API_KEY` in the Asterisk service
environment (systemd `EnvironmentFile=/etc/asterisk/mazh.env`, mode
`640 root:asterisk`). The AGI reads that file itself as a fallback when the
running service env is stale. The AGI uses HTTPS and the `X-Phone-API-Key`
header for backend authentication.

## Text-to-speech (Piper)

The AGI prefers Piper and falls back to `espeak-ng`/`espeak`. Piper must be
installed at `/opt/piper` with a voice model under `/opt/piper/voices/`
(default: `en_US-lessac-medium.onnx`, override with `MAZH_TTS_MODEL`).
Converted speech is cached as 8 kHz mono WAV in `MAZH_TTS_CACHE_DIR`
(default: `/usr/share/asterisk/sounds/en/mazh/generated`), which must be
writable by the `asterisk` user. `sox` must be installed for the 8 kHz
conversion.

Optional environment variables: `MAZH_TTS_MODEL`, `MAZH_TTS_CACHE_DIR`,
`MAZH_TTS_VOICE` (espeak fallback only), `MAZH_TTS_SPEED` (espeak fallback
only).

## Required recordings

The fixed IVR prompts (`welcome`, `enter-pin`, `invalid-pin`, `backend-error`,
`menu`, `goodbye`, `no-input`, `sms-sent`) are generated with the same TTS
backend. Regenerate them any time:

```sh
python3 asterisk/tts_prompts.py
```

The generated 8 kHz WAVs live in `asterisk/sounds/mazh/` and are deployed with
the rest of the configuration. Dynamic weather text is synthesized per-phrase
and cached by the AGI; there is no Festival dependency.

## Test

Call the configured number and enter:

```text
600001#
1
```

The backend must have `PHONE_API_KEY` configured to the same value as
`MAZH_PHONE_API_KEY`. Never expose that key in a browser or commit it.
