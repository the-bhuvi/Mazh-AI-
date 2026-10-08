import logging
import httpx
import asyncio
from typing import Dict, Any
from app.providers.base import BaseWeatherProvider
from app.config import OPEN_METEO_FORECAST_URL

logger = logging.getLogger(__name__)

# WMO Weather Code Mappings to Plain-Language Condition
WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}

def wind_deg_to_direction(deg: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((deg + 22.5) // 45) % 8
    return dirs[idx]

class OpenMeteoProvider(BaseWeatherProvider):
    def __init__(self, timeout: float = 2.0, max_retries: int = 1):
        self.timeout = timeout
        self.max_retries = max_retries
        self.url = OPEN_METEO_FORECAST_URL

    async def get_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,weather_code",
            "hourly": "temperature_2m,precipitation_probability,precipitation",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
            "forecast_days": 7,
            "timezone": "Asia/Kolkata"
        }

        last_error = None
        for attempt in range(1 + self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(self.url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    return self._normalize_data(data, lat, lon)
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    retry_after = e.response.headers.get("Retry-After")
                    try:
                        delay = max(float(retry_after), 1.0) if retry_after else 5.0
                    except ValueError:
                        delay = 5.0
                    logger.warning(
                        "OpenMeteo rate limit reached for lat=%s, lon=%s (attempt %s/%s)",
                        lat,
                        lon,
                        attempt + 1,
                        1 + self.max_retries,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(delay, 60.0))
                    continue
                logger.warning(
                    "OpenMeteo fetch attempt %s failed for lat=%s, lon=%s: %s",
                    attempt + 1,
                    lat,
                    lon,
                    e,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "OpenMeteo fetch attempt %s failed for lat=%s, lon=%s: %s",
                    attempt + 1,
                    lat,
                    lon,
                    e,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(0.2)

        raise RuntimeError(f"Open-Meteo provider unavailable: {last_error}")

    def _normalize_data(self, raw: Dict[str, Any], lat: float, lon: float) -> Dict[str, Any]:
        current_raw = raw.get("current", {})
        hourly_raw = raw.get("hourly", {})
        daily_raw = raw.get("daily", {})

        wmo_code = current_raw.get("weather_code", 0)
        condition_str = WMO_CODES.get(wmo_code, "Partly cloudy")

        current = {
            "temp_c": float(current_raw.get("temperature_2m", 28.0)),
            "feels_like_c": float(current_raw.get("apparent_temperature", 29.5)),
            "humidity": int(current_raw.get("relative_humidity_2m", 75)),
            "pressure_hpa": float(current_raw.get("surface_pressure", 1012.0)),
            "wind_kph": float(current_raw.get("wind_speed_10m", 12.0)),
            "wind_dir": wind_deg_to_direction(float(current_raw.get("wind_direction_10m", 90.0))),
            "condition": condition_str
        }

        # Format hourly (limit to next 48h)
        hourly_times = hourly_raw.get("time", [])
        hourly_temps = hourly_raw.get("temperature_2m", [])
        hourly_probs = hourly_raw.get("precipitation_probability", [])
        hourly_rains = hourly_raw.get("precipitation", [])

        hourly = []
        limit_h = min(48, len(hourly_times))
        for i in range(limit_h):
            t_str = hourly_times[i]
            # Ensure ISO8601 formatting
            if not t_str.endswith("Z") and "+" not in t_str and len(t_str) == 16:
                t_str += ":00+05:30"
            hourly.append({
                "time": t_str,
                "temp_c": float(hourly_temps[i]) if i < len(hourly_temps) else current["temp_c"],
                "rain_prob": int(hourly_probs[i]) if i < len(hourly_probs) and hourly_probs[i] is not None else 0,
                "rain_mm": float(hourly_rains[i]) if i < len(hourly_rains) and hourly_rains[i] is not None else 0.0
            })

        # Format daily (7 days)
        daily_dates = daily_raw.get("time", [])
        daily_maxs = daily_raw.get("temperature_2m_max", [])
        daily_mins = daily_raw.get("temperature_2m_min", [])
        daily_probs = daily_raw.get("precipitation_probability_max", [])
        daily_rains = daily_raw.get("precipitation_sum", [])

        daily = []
        limit_d = min(7, len(daily_dates))
        for i in range(limit_d):
            daily.append({
                "date": str(daily_dates[i]),
                "min_c": float(daily_mins[i]) if i < len(daily_mins) else 24.0,
                "max_c": float(daily_maxs[i]) if i < len(daily_maxs) else 33.0,
                "rain_prob": int(daily_probs[i]) if i < len(daily_probs) and daily_probs[i] is not None else 0,
                "rain_mm": float(daily_rains[i]) if i < len(daily_rains) and daily_rains[i] is not None else 0.0
            })

        return {
            "lat": lat,
            "lon": lon,
            "current": current,
            "hourly": hourly,
            "daily": daily
        }
