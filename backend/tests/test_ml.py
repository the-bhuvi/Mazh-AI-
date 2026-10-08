import pandas as pd
import pytest

from ml.features import FEATURE_COLUMNS, build_inference_features, build_training_frame, split_by_time
from app.ml_engine import is_in_ml_coverage
from app.engine.insight import build_insight


def _rows():
    rows = []
    for year in (2022, 2023, 2024):
        for hour in range(12):
            rows.append({
                "city_id": "test",
                "time": f"{year}-01-01T{hour:02d}:00:00Z",
                "temperature_c": 28,
                "humidity_pct": 80,
                "pressure_hpa": 1010 - hour,
                "wind_kph": 10,
                "precipitation_mm": 2 if hour >= 8 else 0,
                "forecast_rain_prob": 70,
                "forecast_rain_mm": 12,
                "lat": 11.0,
                "lon": 78.0,
                "elevation_m": 100,
                "enso_anom": 0.5,
                "enso_state": "el_nino",
            })
    return pd.DataFrame(rows)


def test_feature_builder_does_not_use_future_rain_as_a_feature():
    frame = build_training_frame(_rows(), threshold_mm=10)
    early = frame.iloc[0]
    assert set(FEATURE_COLUMNS).issubset(frame.columns)
    assert early["target"] in (0, 1)
    assert early["recent_rain_6h"] == 0
    assert "future_rain_mm" in frame.columns


def test_time_split_has_no_year_overlap():
    frame = build_training_frame(_rows(), threshold_mm=10)
    train, validation, test = split_by_time(frame)
    years = lambda data: set(pd.to_datetime(data["time"], utc=True).dt.year)
    assert years(train).isdisjoint(years(validation))
    assert years(train).isdisjoint(years(test))
    assert years(validation).isdisjoint(years(test))
    assert max(years(train)) < min(years(validation)) < min(years(test))


def test_inference_features_are_contract_ordered_and_future_safe():
    frame = build_inference_features(
        current={"temp_c": 29, "humidity": 85, "pressure_hpa": 1008, "wind_kph": 15},
        hourly=[{"rain_prob": 80, "rain_mm": 3}],
        lat=11,
        lon=78,
        enso_state="neutral",
    )
    assert list(frame.columns) == FEATURE_COLUMNS
    assert frame.iloc[0]["recent_rain_6h"] == 0
    assert frame.iloc[0]["forecast_rain_mm_6h"] == 3


def test_out_of_coverage_is_false():
    assert is_in_ml_coverage(40.0, -73.0) is False


def test_forced_fallback_never_marks_ml_as_used():
    weather = {
        "current": {
            "temp_c": 28, "feels_like_c": 29, "humidity": 80,
            "pressure_hpa": 1010, "wind_kph": 10, "wind_dir": "E",
            "condition": "Cloudy",
        },
        "hourly": [{"time": "2026-01-01T00:00:00Z", "temp_c": 28, "rain_prob": 20, "rain_mm": 0}],
        "daily": [{"date": "2026-01-01", "min_c": 24, "max_c": 31, "rain_prob": 20, "rain_mm": 0}],
    }
    insight = build_insight(
        weather,
        {"name": "Chennai", "lat": 13.08, "lon": 80.27},
        {"enso_state": "unknown", "nino34_anom": None},
        force_fallback=True,
    )
    assert insight["meta"]["ml_used"] is False
    assert insight["meta"]["fallback_used"] is True
