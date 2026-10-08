# Voice IVR latency report

The benchmark uses the local ASGI app and a warmed Chennai cache. It sends the
same DTMF menu request ten times after the greeting, language, PIN lookup, and
PIN confirmation steps. Run:

```powershell
cd backend
python scripts/benchmark_voice.py
```

This measures application response time, not carrier audio delivery or a cold
Open-Meteo request. The target is approximately 1.5 seconds from keypress to
the next audio instruction. Cache hits use the small TwiML response path;
insight computation is started in the background immediately after PIN
confirmation. TTS misses can exceed the target and therefore fall back to
Twilio `<Say>` unless an audio cache is already available.
