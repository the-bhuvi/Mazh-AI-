import logging
import httpx
import asyncio
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from app.providers.open_meteo import WMO_CODES, wind_deg_to_direction

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class HistoricalWeatherProvider:
    """Fetches historical weather data from the Open-Meteo Archive API."""

    def __init__(self, timeout: float = 10.0, max_retries: int = 1):
        self.timeout = timeout
        self.max_retries = max_retries

    async def get_historical_weather(
        self,
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Fetch hourly historical temperature data for a date range.

        Args:
            lat: Latitude
            lon: Longitude
            start_date: ISO date string, e.g. "2026-09-22"
            end_date:   ISO date string, e.g. "2026-10-06"

        Returns:
            Normalised dict with keys: lat, lon, start_date, end_date, hourly
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": "temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code",
            "timezone": "auto",
        }

        last_error = None
        for attempt in range(1 + self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(ARCHIVE_URL, params=params)
                    response.raise_for_status()
                    data = response.json()
                    return self._normalize(data, lat, lon, start_date, end_date)
            except Exception as e:
                logger.warning(
                    f"HistoricalWeather fetch attempt {attempt + 1} failed "
                    f"for lat={lat}, lon={lon}: {e}"
                )
                last_error = e
                if attempt < self.max_retries:
                    await asyncio.sleep(0.3)

        raise RuntimeError(f"Open-Meteo Archive API unavailable: {last_error}")

    def _normalize(
        self,
        raw: Dict[str, Any],
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        hourly_raw = raw.get("hourly", {})
        times = hourly_raw.get("time", [])
        temps = hourly_raw.get("temperature_2m", [])
        precips = hourly_raw.get("precipitation", [])
        humidities = hourly_raw.get("relative_humidity_2m", [])
        wind_speeds = hourly_raw.get("wind_speed_10m", [])
        wind_dirs = hourly_raw.get("wind_direction_10m", [])
        weather_codes = hourly_raw.get("weather_code", [])

        hourly: List[Dict[str, Any]] = []
        for i, t in enumerate(times):
            t_str = t if (t.endswith("Z") or "+" in t) else t + ":00"
            wmo = weather_codes[i] if i < len(weather_codes) and weather_codes[i] is not None else 0
            hourly.append({
                "time": t_str,
                "temp_c": float(temps[i]) if i < len(temps) and temps[i] is not None else None,
                "precipitation_mm": float(precips[i]) if i < len(precips) and precips[i] is not None else 0.0,
                "humidity": int(humidities[i]) if i < len(humidities) and humidities[i] is not None else None,
                "wind_kph": float(wind_speeds[i]) if i < len(wind_speeds) and wind_speeds[i] is not None else None,
                "wind_dir": wind_deg_to_direction(float(wind_dirs[i])) if i < len(wind_dirs) and wind_dirs[i] is not None else "N",
                "condition": WMO_CODES.get(int(wmo), "Unknown"),
            })

        # Build daily aggregates from hourly data
        daily_map: Dict[str, Dict[str, Any]] = {}
        for entry in hourly:
            day = entry["time"][:10]
            if day not in daily_map:
                daily_map[day] = {"temps": [], "precip": 0.0}
            if entry["temp_c"] is not None:
                daily_map[day]["temps"].append(entry["temp_c"])
            daily_map[day]["precip"] += entry["precipitation_mm"]

        daily = []
        for day, vals in sorted(daily_map.items()):
            temps_list = vals["temps"]
            daily.append({
                "date": day,
                "min_c": round(min(temps_list), 1) if temps_list else None,
                "max_c": round(max(temps_list), 1) if temps_list else None,
                "avg_c": round(sum(temps_list) / len(temps_list), 1) if temps_list else None,
                "total_precipitation_mm": round(vals["precip"], 2),
            })

        return {
            "lat": lat,
            "lon": lon,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": raw.get("timezone", "UTC"),
            "hourly": hourly,
            "daily": daily,
        }
