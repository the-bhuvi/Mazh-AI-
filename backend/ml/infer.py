from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd

try:
    from app.config import MODEL_PATH
    from ml.features import FEATURE_COLUMNS, build_inference_features
except ModuleNotFoundError:
    from backend.app.config import MODEL_PATH
    from backend.ml.features import FEATURE_COLUMNS, build_inference_features

logger = logging.getLogger(__name__)

REASON_TEXT = {
    "pressure_change_3h": "pressure is changing over the last few hours",
    "pressure_change_6h": "pressure is changing over the last six hours",
    "humidity_pct": "air is very humid",
    "forecast_rain_prob_6h": "the forecast gives a high rain chance",
    "forecast_rain_mm_6h": "the forecast expects notable rain",
    "recent_rain_3h": "rain has already fallen recently",
    "recent_rain_6h": "recent rain is adding to the wet signal",
    "temperature_c": "warm air is adding moisture capacity",
    "wind_kph": "wind is supporting the weather pattern",
    "enso_anom": "the seasonal climate signal is contributing",
}


class RainfallRiskModel:
    def __init__(self, artifact_path: Path = MODEL_PATH):
        self.artifact_path = artifact_path
        self.artifact: dict[str, Any] | None = None

    def load(self) -> None:
        if not self.artifact_path.exists():
            raise FileNotFoundError(f"ML artifact does not exist: {self.artifact_path}")
        artifact = joblib.load(self.artifact_path)
        if not isinstance(artifact, dict) or artifact.get("version") != 2:
            raise ValueError("ML artifact is not a version 2 calibrated rainfall model")
        if artifact.get("feature_names") != FEATURE_COLUMNS:
            raise ValueError("ML artifact feature names do not match the inference contract")
        self.artifact = artifact

    def predict(
        self,
        *,
        current: Mapping[str, float],
        hourly: Sequence[Mapping[str, float]],
        lat: float,
        lon: float,
        elevation_m: float = 0.0,
        enso_anom: float | None = None,
        enso_state: str = "unknown",
    ) -> dict[str, Any]:
        if self.artifact is None:
            self.load()
        assert self.artifact is not None
        features = build_inference_features(
            current=current, hourly=hourly, lat=lat, lon=lon,
            elevation_m=elevation_m, enso_anom=enso_anom, enso_state=enso_state,
        )
        raw_probability = float(self.artifact["model"].predict_proba(features[FEATURE_COLUMNS])[:, 1][0])
        score = float(self.artifact["calibrator"].predict([raw_probability])[0])
        score = max(0.0, min(1.0, score))
        level = "high" if score >= 0.6 else ("moderate" if score >= 0.3 else "low")
        reasons = self._reasons(features, score)
        return {"score": round(score, 3), "level": level, "reasons": reasons}

    def _reasons(self, features: pd.DataFrame, score: float) -> list[str]:
        assert self.artifact is not None
        model = self.artifact["model"]
        contributions = None
        if self.artifact.get("model_kind") == "xgboost":
            try:
                import xgboost as xgb
                contributions = model.get_booster().predict(xgb.DMatrix(features[FEATURE_COLUMNS]), pred_contribs=True)[0][:-1]
            except Exception as exc:
                logger.warning("Could not compute XGBoost contributions: %s", exc)
        if contributions is None:
            contributions = np.zeros(len(FEATURE_COLUMNS))
            values = features.iloc[0]
            if values["forecast_rain_prob_6h"] >= 60:
                contributions[FEATURE_COLUMNS.index("forecast_rain_prob_6h")] = 1
            if values["humidity_pct"] >= 80:
                contributions[FEATURE_COLUMNS.index("humidity_pct")] = 0.8
            if values["forecast_rain_mm_6h"] >= 10:
                contributions[FEATURE_COLUMNS.index("forecast_rain_mm_6h")] = 0.9
        ranked = np.argsort(np.asarray(contributions))[::-1]
        reasons = [REASON_TEXT[name] for name in (FEATURE_COLUMNS[index] for index in ranked[:3]) if np.asarray(contributions)[FEATURE_COLUMNS.index(name)] > 0 and name in REASON_TEXT]
        if not reasons:
            reasons = ["the forecast signal is currently low"] if score < 0.3 else ["several weather signals are pointing to rain"]
        return reasons[:3]


_MODEL = RainfallRiskModel()


def predict_risk(**kwargs) -> dict[str, Any]:
    return _MODEL.predict(**kwargs)
