from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

try:
    from app.config import CONFIG_DIR, ML_DATA_DIR
    from ml.features import City
except ModuleNotFoundError:
    from backend.app.config import CONFIG_DIR, ML_DATA_DIR
    from backend.ml.features import City

logger = logging.getLogger(__name__)
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
NOAA_ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"


def load_cities() -> list[City]:
    payload = json.loads((CONFIG_DIR / "ml_coverage.json").read_text(encoding="utf-8"))
    return [City(**item) for item in payload.get("cities", [])]


def _request(url: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def fetch_city(
    city: City,
    start: date,
    end: date,
    *,
    historical_forecast: bool = True,
) -> pd.DataFrame:
    """Download one city range. The response is saved by cache_raw_data."""
    params = {
        "latitude": city.lat,
        "longitude": city.lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join([
            "temperature_2m", "relative_humidity_2m", "surface_pressure",
            "wind_speed_10m", "precipitation", "precipitation_probability",
        ]),
        "timezone": "UTC",
    }
    url = HISTORICAL_FORECAST_URL if historical_forecast else ARCHIVE_URL
    try:
        payload = _request(url, params)
    except Exception:
        if historical_forecast:
            logger.warning("Historical Forecast API failed for %s; retrying Archive API", city.name)
            payload = _request(ARCHIVE_URL, params)
        else:
            raise
    hourly = payload.get("hourly", {})
    frame = pd.DataFrame({
        "time": hourly.get("time", []),
        "temperature_c": hourly.get("temperature_2m", []),
        "humidity_pct": hourly.get("relative_humidity_2m", []),
        "pressure_hpa": hourly.get("surface_pressure", []),
        "wind_kph": hourly.get("wind_speed_10m", []),
        "precipitation_mm": hourly.get("precipitation", []),
        "forecast_rain_prob": hourly.get("precipitation_probability", []),
        "forecast_rain_mm": hourly.get("precipitation", []),
    })
    frame["city_id"] = city.id
    frame["lat"] = city.lat
    frame["lon"] = city.lon
    frame["elevation_m"] = city.elevation_m
    return frame


def cache_raw_data(frame: pd.DataFrame, sqlite_path: Path | None = None) -> Path:
    sqlite_path = sqlite_path or (ML_DATA_DIR / "raw_weather.sqlite")
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(sqlite_path) as connection:
        frame.to_sql("hourly_weather", connection, if_exists="append", index=False)
    csv_path = sqlite_path.with_suffix(".csv")
    frame.to_csv(csv_path, mode="a", header=not csv_path.exists(), index=False)
    return sqlite_path


def fetch_enso_text(cache_path: Path | None = None) -> str:
    cache_path = cache_path or (ML_DATA_DIR / "oni.ascii.txt")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    with httpx.Client(timeout=30.0) as client:
        response = client.get(NOAA_ONI_URL)
        response.raise_for_status()
    cache_path.write_text(response.text, encoding="utf-8")
    return response.text


def parse_enso(text: str) -> pd.DataFrame:
    """Parse CPC ONI table lines: season, year, total, anomaly, ..."""
    records = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4 or not fields[1].lstrip("-").isdigit():
            continue
        try:
            year = int(fields[1])
            anomaly = float(fields[3])
        except ValueError:
            continue
        month = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                 "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}.get(fields[0])
        if month:
            records.append({"year": year, "month": month, "enso_anom": anomaly})
    result = pd.DataFrame(records)
    if result.empty:
        return result
    result["enso_state"] = result["enso_anom"].map(lambda value: "el_nino" if value >= 0.5 else ("la_nina" if value <= -0.5 else "neutral"))
    return result.drop_duplicates(["year", "month"]).sort_values(["year", "month"])


def join_enso(frame: pd.DataFrame, enso: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["time"] = pd.to_datetime(result["time"], utc=True)
    if enso.empty:
        result["enso_anom"], result["enso_state"] = 0.0, "unknown"
        return result
    result["year"] = result["time"].dt.year
    result["month"] = result["time"].dt.month
    return result.merge(enso, on=["year", "month"], how="left").drop(columns=["year", "month"]).assign(
        enso_anom=lambda data: data["enso_anom"].fillna(0.0),
        enso_state=lambda data: data["enso_state"].fillna("unknown"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and cache ML training weather data.")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=(date.today() - timedelta(days=2)).isoformat())
    parser.add_argument("--archive", action="store_true", help="Use Archive API instead of Historical Forecast API.")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    for city in load_cities():
        logger.info("Downloading %s", city.name)
        cache_raw_data(fetch_city(city, start, end, historical_forecast=not args.archive))
    fetch_enso_text()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
