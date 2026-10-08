from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import BASE_DIR

PHRASES = json.loads(
    (Path(__file__).with_name("phrases.json")).read_text(encoding="utf-8")
)


def phrase(lang: str, key: str, **values: Any) -> str:
    template = PHRASES.get(lang, PHRASES["en"]).get(key, PHRASES["en"][key])
    return template.format(**values)


def _format_window(risk: dict[str, Any], lang: str) -> str:
    window = risk.get("window", {})
    try:
        start = datetime.fromisoformat(window["start"].replace("Z", "+00:00")).strftime("%I:%M %p").lstrip("0")
        end = datetime.fromisoformat(window["end"].replace("Z", "+00:00")).strftime("%I:%M %p").lstrip("0")
        return f"Rain is most likely between {start} and {end}." if lang == "en" else f"மழை {start} முதல் {end} வரை அதிகம் இருக்கலாம்."
    except (KeyError, ValueError, TypeError):
        return "Rain timing is uncertain." if lang == "en" else "மழை நேரம் தெளிவாக இல்லை."


def render_insight(insight: dict[str, Any], lang: str, view: str) -> str:
    location = insight["location"]["name"]
    current = insight["current"]
    daily = insight.get("daily", [])
    rain = next((item for item in insight.get("risks", []) if item["type"] == "heavy_rain"), None)
    rain = rain or {"level": "low", "window": {}}
    recommendation = insight["insight"].get("recommendations", ["Plan carefully."])[0]

    if view == "rain":
        return phrase(lang, "rain", location=location, level=rain["level"], window=_format_window(rain, lang), recommendation=recommendation)
    if view == "tomorrow":
        tomorrow = daily[1] if len(daily) > 1 else (daily[0] if daily else {})
        return phrase(lang, "tomorrow", location=location, rain_prob=tomorrow.get("rain_prob", 0), rain_mm=tomorrow.get("rain_mm", 0), recommendation=recommendation)
    if view == "alerts":
        high = [item["type"].replace("_", " ") for item in insight.get("risks", []) if item["level"] == "high"]
        alerts = ", ".join(high) if high else ("no high alerts right now" if lang == "en" else "தற்போது அதிக அபாய எச்சரிக்கை இல்லை")
        return phrase(lang, "alerts", location=location, alerts=alerts, recommendation=recommendation)
    temperature = f"{current.get('temp_c', 0):.0f} degrees Celsius" if lang == "en" else f"{current.get('temp_c', 0):.0f} டிகிரி செல்சியஸ்"
    return phrase(lang, "today", location=location, temperature=temperature, summary=insight["insight"]["summary"])
