"""Runtime adapter for the versioned rainfall-risk ML artifact.

The adapter is intentionally fail-closed: an unavailable, incompatible, or
failed model never changes the forecast-only insight path.
"""

import json
import logging
from typing import Any, Dict, Optional

from app.config import ML_COVERAGE_FILE, ML_ENABLED

logger = logging.getLogger(__name__)

_ml_coverage_bounds: Optional[Dict[str, float]] = None
_elevation_by_city: dict[str, float] = {}


def load_ml_config_and_model():
    global _ml_coverage_bounds, _elevation_by_city
    try:
        payload = json.loads(ML_COVERAGE_FILE.read_text(encoding="utf-8"))
        _ml_coverage_bounds = payload.get("bounding_box", {})
        _elevation_by_city = {
            item["id"]: float(item.get("elevation_m", 0.0))
            for item in payload.get("cities", [])
        }
    except Exception as exc:
        logger.error("Failed to load ML coverage configuration: %s", exc)
        _ml_coverage_bounds = None
        _elevation_by_city = {}


load_ml_config_and_model()


def preload_ml_model() -> bool:
    """Load and validate the model once during application startup."""
    try:
        from ml.infer import _MODEL
        _MODEL.load()
        logger.info("Rainfall ML model preloaded")
        return True
    except Exception as exc:
        logger.warning("Rainfall ML model unavailable; forecast-only fallback will be used: %s", exc)
        return False


def is_in_ml_coverage(lat: float, lon: float) -> bool:
    if not ML_ENABLED or not _ml_coverage_bounds:
        return False
    return (
        _ml_coverage_bounds.get("min_lat", 8.0) <= lat <= _ml_coverage_bounds.get("max_lat", 13.8)
        and _ml_coverage_bounds.get("min_lon", 76.0) <= lon <= _ml_coverage_bounds.get("max_lon", 80.6)
    )


def _elevation_for(lat: float, lon: float) -> float:
    # Coordinates in the coverage file are used only as a small inference hint.
    # Unknown locations remain at sea-level rather than receiving a guessed value.
    if abs(lat - 11.4102) < 0.1 and abs(lon - 76.6950) < 0.1:
        return _elevation_by_city.get("ooty", 0.0)
    return 0.0


def predict_ml_risk(
    hourly: list,
    current: dict,
    lat: float,
    lon: float,
    enso_anom: float | None = None,
    enso_state: str = "unknown",
) -> Dict[str, Any]:
    if not is_in_ml_coverage(lat, lon):
        raise RuntimeError("Location is outside ML coverage or ML is disabled")
    try:
        from ml.infer import predict_risk
    except ModuleNotFoundError:
        from backend.ml.infer import predict_risk

    return predict_risk(
        current=current,
        hourly=hourly,
        lat=lat,
        lon=lon,
        elevation_m=_elevation_for(lat, lon),
        enso_anom=enso_anom,
        enso_state=enso_state,
    )
