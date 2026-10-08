import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from app.ml_engine import is_in_ml_coverage, predict_ml_risk

logger = logging.getLogger(__name__)

def format_hour(iso_str: str) -> str:
    """Format ISO timestamp into 12-hour AM/PM representation."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        # Adjust to IST (+5:30) if timezone naive or UTC
        if dt.tzinfo is None or dt.tzinfo == timezone.utc:
            dt = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return iso_str

def find_rain_windows(hourly: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identifies rain windows: continuous hours where rain_prob > 60% or rain_mm >= 1.5.
    Returns list of windows with start time, end time, max_prob, and total_mm.
    """
    windows = []
    current_window = None

    for h in hourly[:24]:
        time_str = h["time"]
        prob = h["rain_prob"]
        mm = h["rain_mm"]

        if prob >= 60 or mm >= 1.5:
            if current_window is None:
                current_window = {
                    "start": time_str,
                    "end": time_str,
                    "max_prob": prob,
                    "total_mm": mm,
                    "hours_count": 1
                }
            else:
                current_window["end"] = time_str
                current_window["max_prob"] = max(current_window["max_prob"], prob)
                current_window["total_mm"] += mm
                current_window["hours_count"] += 1
        else:
            if current_window is not None:
                windows.append(current_window)
                current_window = None

    if current_window is not None:
        windows.append(current_window)

    return windows

def build_insight(
    weather_data: Dict[str, Any],
    location_info: Dict[str, Any],
    climate_info: Dict[str, Any],
    force_fallback: bool = False
) -> Dict[str, Any]:
    """
    Engine that constructs the full Insight object adhering to the strict INSIGHT SCHEMA.
    """
    lat = location_info["lat"]
    lon = location_info["lon"]
    place_name = location_info.get("name", f"Location ({lat}, {lon})")

    current = weather_data["current"]
    hourly = weather_data["hourly"]
    daily = weather_data["daily"]

    # Check ML coverage
    ml_eligible = is_in_ml_coverage(lat, lon) and not force_fallback
    ml_used = False
    fallback_used = not ml_eligible or force_fallback

    # ML rainfall prediction attempt
    ml_score, ml_level, ml_conf = 0.0, "low", 0.85
    ml_reasons: List[str] = []
    if ml_eligible:
        try:
            nino_anom = climate_info.get("nino34_anom") or 0.0
            prediction = predict_ml_risk(
                hourly, current, lat=lat, lon=lon,
                enso_anom=nino_anom,
                enso_state=climate_info.get("enso_state", "unknown"),
            )
            ml_score = float(prediction["score"])
            ml_level = str(prediction["level"])
            ml_reasons = list(prediction.get("reasons", []))
            ml_conf = max(0.5, min(0.99, 1.0 - abs(ml_score - 0.5)))
            ml_used = True
            fallback_used = False
        except Exception as e:
            logger.warning(f"ML inference failed, using rule fallback: {e}")
            ml_used = False
            fallback_used = True

    # Identify rain windows
    rain_windows = find_rain_windows(hourly)
    next_24h = hourly[:24]
    max_prob_24h = max(([h["rain_prob"] for h in next_24h] if next_24h else [0]), default=0)
    rain_sum_24h = sum(h["rain_mm"] for h in next_24h) if next_24h else 0.0

    # Determine default window start & end
    now_iso = datetime.now(timezone.utc).isoformat()
    if rain_windows:
        win_start = rain_windows[0]["start"]
        win_end = rain_windows[0]["end"]
    elif next_24h:
        win_start = next_24h[0]["time"]
        win_end = next_24h[min(5, len(next_24h)-1)]["time"]
    else:
        win_start = now_iso
        win_end = now_iso

    # 1. Heavy Rain Risk
    if ml_used:
        rain_score = ml_score
        rain_level = ml_level
        rain_conf = ml_conf
    else:
        if max_prob_24h >= 75 or rain_sum_24h >= 30.0:
            rain_score, rain_level = 0.85, "high"
        elif max_prob_24h >= 50 or rain_sum_24h >= 10.0:
            rain_score, rain_level = 0.55, "moderate"
        else:
            rain_score, rain_level = 0.15, "low"
        rain_conf = 0.90

    rain_reasons = list(ml_reasons)
    if not rain_reasons:
        rain_reasons = []
    if rain_windows:
        w = rain_windows[0]
        start_fmt = format_hour(w["start"])
        end_fmt = format_hour(w["end"])
        rain_reasons.append(f"Continuous rain expected between {start_fmt} and {end_fmt}.")
        rain_reasons.append(f"Rain probability peaks at {w['max_prob']}% with around {round(w['total_mm'], 1)} mm rain.")
    elif max_prob_24h > 30:
        rain_reasons.append(f"Scattered rain chances up to {max_prob_24h}% expected today.")
    else:
        rain_reasons.append("Low likelihood of rain today.")

    # 2. Heat Risk
    temp_c = current["temp_c"]
    feels_c = current["feels_like_c"]
    if feels_c >= 42.0 or temp_c >= 40.0:
        heat_score, heat_level = 0.85, "high"
        heat_reasons = [f"Extreme heat warning: temperature is {temp_c}°C (feels like {feels_c}°C)."]
    elif feels_c >= 38.0 or temp_c >= 36.0:
        heat_score, heat_level = 0.50, "moderate"
        heat_reasons = [f"Warm condition: feels like {feels_c}°C with high humidity."]
    else:
        heat_score, heat_level = 0.10, "low"
        heat_reasons = [f"Comfortable thermal conditions ({temp_c}°C)."]

    # 3. Wind Risk
    wind_kph = current["wind_kph"]
    if wind_kph >= 45.0:
        wind_score, wind_level = 0.80, "high"
        wind_reasons = [f"Strong gusty winds up to {wind_kph} km/h detected."]
    elif wind_kph >= 25.0:
        wind_score, wind_level = 0.45, "moderate"
        wind_reasons = [f"Breezy conditions with wind speeds of {wind_kph} km/h."]
    else:
        wind_score, wind_level = 0.10, "low"
        wind_reasons = [f"Gentle wind speeds around {wind_kph} km/h."]

    # 4. Flood Risk
    enso_active = climate_info.get("enso_state") == "el_nino"
    if rain_sum_24h >= 60.0 or (enso_active and rain_sum_24h >= 40.0):
        flood_score, flood_level = 0.85, "high"
        flood_reasons = [f"Heavy cumulative rainfall ({round(rain_sum_24h, 1)} mm) raises waterlogging risk in low-lying areas."]
    elif rain_sum_24h >= 20.0:
        flood_score, flood_level = 0.45, "moderate"
        flood_reasons = [f"Moderate 24-hour rainfall ({round(rain_sum_24h, 1)} mm) may cause localized street pooling."]
    else:
        flood_score, flood_level = 0.05, "low"
        flood_reasons = ["Minimal flood or drainage risk for this area."]

    risks = [
        {
            "type": "heavy_rain",
            "score": rain_score,
            "level": rain_level,
            "window": {"start": win_start, "end": win_end},
            "confidence": rain_conf,
            "reasons": rain_reasons
        },
        {
            "type": "heat",
            "score": heat_score,
            "level": heat_level,
            "window": {"start": win_start, "end": win_end},
            "confidence": 0.95,
            "reasons": heat_reasons
        },
        {
            "type": "wind",
            "score": wind_score,
            "level": wind_level,
            "window": {"start": win_start, "end": win_end},
            "confidence": 0.90,
            "reasons": wind_reasons
        },
        {
            "type": "flood",
            "score": flood_score,
            "level": flood_level,
            "window": {"start": win_start, "end": win_end},
            "confidence": 0.85,
            "reasons": flood_reasons
        }
    ]

    # Generate Plain-Language Summary & Recommendations
    summary, recs = generate_plain_summary(place_name, rain_level, rain_windows, max_prob_24h, current, climate_info)

    # Generate SMS text (<300 characters)
    sms = generate_sms_text(place_name, rain_level, rain_windows, max_prob_24h)

    # Format ISO timestamp
    gen_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    sources = ["Open-Meteo API"]
    if ml_used:
        sources.append("Tamil Nadu ML Risk Engine")

    insight_obj = {
        "location": {
            "name": place_name,
            "lat": lat,
            "lon": lon
        },
        "generated_at": gen_at,
        "current": current,
        "hourly": hourly,
        "daily": daily,
        "risks": risks,
        "insight": {
            "summary": summary,
            "recommendations": recs,
            "sms_text": sms
        },
        "meta": {
            "sources": sources,
            "ml_used": ml_used,
            "fallback_used": fallback_used,
            "climate": {
                "enso_state": climate_info.get("enso_state", "unknown"),
                "nino34_anom": climate_info.get("nino34_anom")
            }
        }
    }

    return insight_obj

def generate_plain_summary(
    place_name: str,
    rain_level: str,
    rain_windows: List[Dict[str, Any]],
    max_prob: int,
    current: Dict[str, Any],
    climate_info: Dict[str, Any]
) -> Tuple[str, List[str]]:

    enso = climate_info.get("enso_state")
    el_nino_str = " (El Niño active)" if enso == "el_nino" else ""

    if rain_windows:
        w = rain_windows[0]
        start_t = format_hour(w["start"])
        end_t = format_hour(w["end"])
        if rain_level == "high":
            summary = f"Heavy rain is expected in {place_name} between {start_t} and {end_t}{el_nino_str}. High likelihood of localized downpours."
            recs = [
                f"Plan outdoor activities before {start_t} if possible.",
                "Bring sensitive outdoor items or laundry indoors early.",
                "Drive carefully as visibility may drop during intense spells."
            ]
        elif rain_level == "moderate":
            summary = f"Rain is likely in {place_name} this evening between {start_t} and {end_t} with a {w['max_prob']}% chance. Go out earlier if you can."
            recs = [
                f"Carry an umbrella if you are stepping out between {start_t} and {end_t}.",
                "Check street drainage before parking vehicles."
            ]
        else:
            summary = f"Light scattered showers are possible in {place_name} around {start_t}."
            recs = ["No major rainfall disruption expected today."]
    elif max_prob > 30:
        summary = f"Overcast skies in {place_name} with up to {max_prob}% chance of brief showers today."
        recs = ["Keep a light raincoat or umbrella handy just in case."]
    else:
        summary = f"{place_name} will experience mostly clear to partly cloudy weather today with current temperature at {current['temp_c']}°C."
        recs = ["Good conditions for outdoor activities and travel."]

    return summary, recs

def generate_sms_text(
    place_name: str,
    rain_level: str,
    rain_windows: List[Dict[str, Any]],
    max_prob: int
) -> str:
    """Generates concise SMS notification text under 300 characters."""
    if rain_windows:
        w = rain_windows[0]
        st = format_hour(w["start"])
        et = format_hour(w["end"])
        msg = f"[Mazh AI Alert] Rain expected in {place_name} between {st} & {et} ({w['max_prob']}% prob). Risk: {rain_level.upper()}. Carry umbrella & avoid low-lying roads. Info: mazh.ai"
    elif max_prob > 30:
        msg = f"[Mazh AI Alert] {place_name}: {max_prob}% chance of rain today. Scattered showers possible. Info: mazh.ai"
    else:
        msg = f"[Mazh AI Alert] {place_name}: Weather clear today. Low rain risk. Have a safe day! Info: mazh.ai"

    # Truncate if exceeds 295 chars
    if len(msg) > 295:
        msg = msg[:292] + "..."
    return msg
