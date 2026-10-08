from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "temperature_c",
    "humidity_pct",
    "pressure_hpa",
    "pressure_change_3h",
    "pressure_change_6h",
    "wind_kph",
    "recent_rain_1h",
    "recent_rain_3h",
    "recent_rain_6h",
    "forecast_rain_prob_6h",
    "forecast_rain_mm_6h",
    "hour",
    "month",
    "lat",
    "lon",
    "elevation_m",
    "enso_anom",
    "enso_state_code",
]

ENSO_CODES = {"unknown": 0, "neutral": 1, "el_nino": 2, "la_nina": -1}


@dataclass(frozen=True)
class City:
    id: str
    name: str
    lat: float
    lon: float
    elevation_m: float = 0.0


def _numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _ensure_time(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["time"] = pd.to_datetime(result["time"], utc=True, errors="coerce")
    return result.dropna(subset=["time"]).sort_values(["city_id", "time"])


def build_training_frame(
    rows: pd.DataFrame,
    threshold_mm: float = 10.0,
    horizon_hours: int = 6,
) -> pd.DataFrame:
    """Build leakage-safe features and a future six-hour rainfall target.

    The target is created from shifted precipitation only. Every feature uses
    the observation at t or earlier, except forecast columns supplied by the
    provider as predictions available at t.
    """
    if rows.empty:
        return pd.DataFrame(columns=[*FEATURE_COLUMNS, "target", "time", "city_id"])
    frame = _ensure_time(rows)
    required = {"city_id", "time", "precipitation_mm"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Training data is missing columns: {sorted(missing)}")

    for column in (
        "temperature_c", "humidity_pct", "pressure_hpa", "wind_kph",
        "forecast_rain_prob", "forecast_rain_mm", "lat", "lon",
        "elevation_m", "enso_anom",
    ):
        if column not in frame:
            frame[column] = 0.0
        frame[column] = _numeric(frame[column])
    if "enso_state" not in frame:
        frame["enso_state"] = "unknown"

    grouped = frame.groupby("city_id", sort=False, group_keys=False)
    frame["pressure_change_3h"] = grouped["pressure_hpa"].diff(3)
    frame["pressure_change_6h"] = grouped["pressure_hpa"].diff(6)
    frame["recent_rain_1h"] = grouped["precipitation_mm"].shift(1)
    frame["recent_rain_3h"] = grouped["precipitation_mm"].shift(1).rolling(3, min_periods=1).sum().reset_index(level=0, drop=True)
    frame["recent_rain_6h"] = grouped["precipitation_mm"].shift(1).rolling(6, min_periods=1).sum().reset_index(level=0, drop=True)
    # A historical hourly row represents the forecast available for that hour.
    # Do not aggregate forecast columns from t+1 onward: that would leak future
    # forecast issues into the t feature row.
    frame["forecast_rain_prob_6h"] = frame["forecast_rain_prob"]
    frame["forecast_rain_mm_6h"] = frame["forecast_rain_mm"]
    future_rain = sum(grouped["precipitation_mm"].shift(-offset) for offset in range(1, horizon_hours + 1))
    frame["future_rain_mm"] = future_rain
    frame["target"] = (frame["future_rain_mm"] >= threshold_mm).astype(int)
    frame["hour"] = frame["time"].dt.hour
    frame["month"] = frame["time"].dt.month
    frame["enso_state_code"] = frame["enso_state"].map(ENSO_CODES).fillna(0)
    return frame.dropna(subset=FEATURE_COLUMNS + ["future_rain_mm"]).reset_index(drop=True)


def build_inference_features(
    *,
    current: Mapping[str, float],
    hourly: Sequence[Mapping[str, float]],
    lat: float,
    lon: float,
    elevation_m: float = 0.0,
    enso_anom: float | None = None,
    enso_state: str = "unknown",
    now: datetime | None = None,
) -> pd.DataFrame:
    """Create exactly one inference row using current and future forecast data."""
    forecast = list(hourly[:6])
    rain_values = [float(item.get("rain_mm", 0.0) or 0.0) for item in forecast]
    probabilities = [float(item.get("rain_prob", 0.0) or 0.0) for item in forecast]
    timestamp = now or datetime.now().astimezone()
    row = {
        "temperature_c": float(current.get("temp_c", 0.0)),
        "humidity_pct": float(current.get("humidity", 0.0)),
        "pressure_hpa": float(current.get("pressure_hpa", 0.0)),
        # The public weather contract contains no pressure history. Keep this
        # explicitly neutral instead of accidentally using future forecast data.
        "pressure_change_3h": 0.0,
        "pressure_change_6h": 0.0,
        "wind_kph": float(current.get("wind_kph", 0.0)),
        "recent_rain_1h": 0.0,
        "recent_rain_3h": 0.0,
        "recent_rain_6h": 0.0,
        "forecast_rain_prob_6h": max(probabilities, default=0.0),
        "forecast_rain_mm_6h": sum(rain_values),
        "hour": timestamp.hour,
        "month": timestamp.month,
        "lat": lat,
        "lon": lon,
        "elevation_m": elevation_m,
        "enso_anom": float(enso_anom or 0.0),
        "enso_state_code": ENSO_CODES.get(enso_state, 0),
    }
    return pd.DataFrame([row], columns=FEATURE_COLUMNS)


def split_by_time(frame: pd.DataFrame, validation_years: int = 1, test_years: int = 1):
    """Return train/validation/test in chronological order, without shuffling."""
    if frame.empty:
        return frame.copy(), frame.copy(), frame.copy()
    years = sorted(pd.to_datetime(frame["time"], utc=True).dt.year.unique())
    if len(years) < validation_years + test_years + 1:
        raise ValueError("At least three calendar years are required for a time split")
    test_year_set = set(years[-test_years:])
    validation_year_set = set(years[-test_years - validation_years:-test_years])
    year_series = pd.to_datetime(frame["time"], utc=True).dt.year
    train = frame[~year_series.isin(test_year_set | validation_year_set)].copy()
    validation = frame[year_series.isin(validation_year_set)].copy()
    test = frame[year_series.isin(test_year_set)].copy()
    return train, validation, test
