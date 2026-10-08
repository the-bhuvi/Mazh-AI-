import json
import logging
import joblib
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from app.config import ML_COVERAGE_FILE, MODEL_PATH

logger = logging.getLogger(__name__)

_model: Optional[Any] = None
_ml_coverage_bounds: Optional[Dict[str, float]] = None

def load_ml_config_and_model():
    global _model, _ml_coverage_bounds

    # Load bounding box
    if ML_COVERAGE_FILE.exists():
        try:
            with open(ML_COVERAGE_FILE, "r", encoding="utf-8") as f:
                cov_data = json.load(f)
                _ml_coverage_bounds = cov_data.get("bounding_box", {})
                logger.info(f"Loaded ML coverage bounds: {_ml_coverage_bounds}")
        except Exception as e:
            logger.error(f"Failed to load ML coverage file: {e}")

    if _ml_coverage_bounds is None:
        # Default Tamil Nadu & Puducherry bounds
        _ml_coverage_bounds = {"min_lat": 8.0, "max_lat": 13.8, "min_lon": 76.0, "max_lon": 80.6}

    # Load trained model into memory
    if MODEL_PATH.exists():
        try:
            _model = joblib.load(MODEL_PATH)
            logger.info(f"Loaded ML model into memory from {MODEL_PATH}")
        except Exception as e:
            logger.error(f"Failed to load ML model from {MODEL_PATH}: {e}")
            _model = None

# Initialize on module import
load_ml_config_and_model()

def is_in_ml_coverage(lat: float, lon: float) -> bool:
    if not _ml_coverage_bounds:
        return False
    min_lat = _ml_coverage_bounds.get("min_lat", 8.0)
    max_lat = _ml_coverage_bounds.get("max_lat", 13.8)
    min_lon = _ml_coverage_bounds.get("min_lon", 76.0)
    max_lon = _ml_coverage_bounds.get("max_lon", 80.6)

    return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

def predict_ml_risk(hourly: list, current: dict, enso_anom: float = 0.0) -> Tuple[float, str, float]:
    """
    Performs ML inference using trained model in memory.
    Returns: (score, level, confidence)
    """
    if _model is None:
        raise RuntimeError("ML model is not loaded in memory")

    # Extract 24h features
    next_24h = hourly[:24] if hourly else []
    max_rain_24h = max(([h["rain_mm"] for h in next_24h] if next_24h else [0.0]), default=0.0)
    max_rain_prob = max(([h["rain_prob"] for h in next_24h] if next_24h else [0]), default=0)

    # 3-hour sliding peak rain
    peak_3h = 0.0
    for i in range(len(next_24h) - 2):
        s3 = sum(next_24h[i + j]["rain_mm"] for j in range(3))
        if s3 > peak_3h:
            peak_3h = s3

    humidity = current.get("humidity", 75)
    pressure = current.get("pressure_hpa", 1012.0)
    press_drop = max(0.0, 1013.25 - pressure)
    wind_kph = current.get("wind_kph", 12.0)

    features = np.array([[max_rain_24h, max_rain_prob, peak_3h, humidity, press_drop, wind_kph, enso_anom]])

    probas = _model.predict_proba(features)[0] # class 0: low, 1: moderate, 2: high
    pred_class = int(np.argmax(probas))

    # Calculate continuous score 0.0 - 1.0
    score = float(probas[1] * 0.5 + probas[2] * 1.0)
    # Ensure score reflects severe precipitation if max rain or prob is extremely high
    if max_rain_prob >= 80 or max_rain_24h >= 40.0:
        score = max(score, 0.75)
    elif max_rain_prob >= 50 or max_rain_24h >= 15.0:
        score = max(score, 0.45)

    level = "high" if score >= 0.70 else ("moderate" if score >= 0.35 else "low")
    confidence = float(np.max(probas))

    return round(score, 2), level, round(confidence, 2)
