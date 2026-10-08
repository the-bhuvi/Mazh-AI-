# Mazh AI Asterisk IVR

This directory contains the phone-provider configuration for a Linux Asterisk
server. Asterisk handles the call and DTMF; the FastAPI backend handles PIN
lookup, weather, ML, and deterministic voice text.

## Install

Install Asterisk with the `app_read`, `app_playback`, `app_dial`, `app_hangup`,
`app_goto`, `app_verbose`, and `res_agi` modules. Copy:

- `extensions.conf` into the active dialplan
- `agi/mazh_weather.py` into `/var/lib/asterisk/agi-bin/`
- `sounds/` recordings into the Asterisk sounds directory

The SIP provider must route the incoming number to extension `s`.

Set `MAZH_API_URL` and `MAZH_PHONE_API_KEY` in the Asterisk service
environment, not in the dialplan. The AGI uses HTTPS and the `X-Phone-API-Key`
header for backend authentication.

## Required recordings

Record or generate these fixed files in `sounds/mazh/`:

`welcome`, `enter-pin`, `invalid-pin`, `backend-error`, `menu`, `goodbye`,
`no-input`, and `sms-sent`.

Dynamic weather text is spoken with the configured Asterisk TTS application
(`Festival` in the sample dialplan). Replace `Festival()` with `Say()` or a
pre-generated audio service if your installation uses another TTS engine.

## Test

Call the configured number and enter:

```text
600001#
1
```

The backend must have `PHONE_API_KEY` configured to the same value as
`MAZH_PHONE_API_KEY`. Never expose that key in a browser or commit it.
