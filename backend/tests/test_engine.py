import pytest
from app.engine.insight import find_rain_windows, build_insight

def test_rain_window_detection():
    hourly = [
        {"time": "2026-10-08T10:00:00+05:30", "temp_c": 28.0, "rain_prob": 20, "rain_mm": 0.0},
        {"time": "2026-10-08T11:00:00+05:30", "temp_c": 27.5, "rain_prob": 70, "rain_mm": 2.5},
        {"time": "2026-10-08T12:00:00+05:30", "temp_c": 27.0, "rain_prob": 85, "rain_mm": 5.0},
        {"time": "2026-10-08T13:00:00+05:30", "temp_c": 28.0, "rain_prob": 30, "rain_mm": 0.0}
    ]
    
    windows = find_rain_windows(hourly)
    assert len(windows) == 1
    assert windows[0]["start"] == "2026-10-08T11:00:00+05:30"
    assert windows[0]["end"] == "2026-10-08T12:00:00+05:30"
    assert windows[0]["max_prob"] == 85
    assert windows[0]["total_mm"] == 7.5

def test_build_insight_schema_compliance():
    weather_data = {
        "lat": 13.08,
        "lon": 80.27,
        "current": {"temp_c": 31.0, "feels_like_c": 34.0, "humidity": 70, "pressure_hpa": 1010.0, "wind_kph": 15.0, "wind_dir": "NE", "condition": "Partly cloudy"},
        "hourly": [{"time": "2026-10-08T17:00:00+05:30", "temp_c": 30.0, "rain_prob": 75, "rain_mm": 4.0}],
        "daily": [{"date": "2026-10-08", "min_c": 25.0, "max_c": 33.0, "rain_prob": 75, "rain_mm": 4.0}]
    }
    location_info = {"name": "Chennai", "lat": 13.08, "lon": 80.27}
    climate_info = {"enso_state": "el_nino", "nino34_anom": 1.2}

    insight = build_insight(weather_data, location_info, climate_info)
    
    assert insight["location"]["name"] == "Chennai"
    assert len(insight["risks"]) == 4
    assert len(insight["insight"]["sms_text"]) <= 300
    assert insight["meta"]["climate"]["enso_state"] == "el_nino"
