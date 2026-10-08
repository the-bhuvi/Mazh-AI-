from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score
from xgboost import XGBClassifier

try:
    from app.config import MODEL_PATH, RAIN_THRESHOLD_MM
    from ml.features import FEATURE_COLUMNS, build_training_frame, split_by_time
    from ml.data import fetch_enso_text, parse_enso, join_enso
except ModuleNotFoundError:
    from backend.app.config import MODEL_PATH, RAIN_THRESHOLD_MM
    from backend.ml.features import FEATURE_COLUMNS, build_training_frame, split_by_time
    from backend.ml.data import fetch_enso_text, parse_enso, join_enso

logger = logging.getLogger(__name__)


def _safe_pr_auc(y_true, probabilities) -> float:
    return float(average_precision_score(y_true, probabilities)) if sum(y_true) else float("nan")


def _fit_model(kind: str, x_train: pd.DataFrame, y_train: pd.Series, feature_names: list[str] = FEATURE_COLUMNS):
    if kind == "xgboost":
        positives = max(1, int(y_train.sum()))
        negatives = max(1, int(len(y_train) - positives))
        model = XGBClassifier(
            n_estimators=180, max_depth=4, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.9, min_child_weight=4,
            reg_lambda=2.0, objective="binary:logistic", eval_metric="logloss",
            scale_pos_weight=negatives / positives, random_state=42,
            n_jobs=2, tree_method="hist",
        )
    else:
        model = RandomForestClassifier(
            n_estimators=240, min_samples_leaf=5, class_weight="balanced_subsample",
            random_state=42, n_jobs=2,
        )
    model.fit(x_train[feature_names], y_train)
    return model


def _raw_probability(model, frame: pd.DataFrame, feature_names: list[str] = FEATURE_COLUMNS) -> np.ndarray:
    return np.asarray(model.predict_proba(frame[feature_names])[:, 1], dtype=float)


def _fit_isotonic(model, validation: pd.DataFrame, feature_names: list[str] = FEATURE_COLUMNS) -> IsotonicRegression:
    raw = _raw_probability(model, validation, feature_names)
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw, validation["target"].to_numpy())
    return calibrator


def _calibrated_probability(model, calibrator, frame: pd.DataFrame, feature_names: list[str] = FEATURE_COLUMNS) -> np.ndarray:
    return np.asarray(calibrator.predict(_raw_probability(model, frame, feature_names)), dtype=float)


def _threshold(probabilities: np.ndarray, targets: np.ndarray) -> float:
    candidates = np.arange(0.3, 0.81, 0.05)
    best = (0.6, -1.0)
    for candidate in candidates:
        predicted = probabilities >= candidate
        if not predicted.any():
            continue
        precision = precision_score(targets, predicted, zero_division=0)
        recall = recall_score(targets, predicted, zero_division=0)
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        if f1 > best[1]:
            best = (float(candidate), float(f1))
    return best[0]


def evaluate(model, calibrator, frame: pd.DataFrame, baseline: np.ndarray, cutoff: float) -> dict[str, Any]:
    y = frame["target"].to_numpy()
    probabilities = _calibrated_probability(model, calibrator, frame)
    predicted = probabilities >= cutoff
    fraction, mean_predicted = calibration_curve(y, probabilities, n_bins=10, strategy="quantile")
    return {
        "rows": int(len(frame)),
        "event_rate": float(y.mean()) if len(y) else 0.0,
        "brier": float(brier_score_loss(y, probabilities)),
        "pr_auc": _safe_pr_auc(y, probabilities),
        "precision_at_cutoff": float(precision_score(y, predicted, zero_division=0)),
        "recall_at_cutoff": float(recall_score(y, predicted, zero_division=0)),
        "cutoff": cutoff,
        "calibration": [{"observed": float(a), "predicted": float(b)} for a, b in zip(fraction, mean_predicted)],
        "baseline_brier": float(brier_score_loss(y, baseline)),
        "baseline_pr_auc": _safe_pr_auc(y, baseline),
    }


def train(input_path: Path, output_path: Path = MODEL_PATH, threshold_mm: float = RAIN_THRESHOLD_MM) -> dict[str, Any]:
    if input_path.suffix == ".sqlite":
        import sqlite3
        with sqlite3.connect(input_path) as connection:
            rows = pd.read_sql_query("SELECT * FROM hourly_weather", connection)
    else:
        rows = pd.read_csv(input_path)
    rows = rows.drop_duplicates(["city_id", "time"]).reset_index(drop=True)
    try:
        rows = join_enso(rows, parse_enso(fetch_enso_text()))
    except Exception as exc:
        logger.warning("Could not join cached ENSO data; using unknown ENSO features: %s", exc)
    frame = build_training_frame(rows, threshold_mm=threshold_mm)
    if frame.empty:
        raise ValueError("No usable training rows after feature construction.")
    train_frame, validation_frame, test_frame = split_by_time(frame)
    if train_frame["target"].nunique() < 2 or validation_frame["target"].nunique() < 2:
        raise ValueError("Train and validation splits must each contain both target classes.")

    comparison: dict[str, Any] = {}
    fitted = {}
    for kind in ("xgboost", "random_forest"):
        model = _fit_model(kind, train_frame, train_frame["target"])
        calibrator = _fit_isotonic(model, validation_frame)
        validation_prob = _calibrated_probability(model, calibrator, validation_frame)
        comparison[kind] = {
            "brier": float(brier_score_loss(validation_frame["target"], validation_prob)),
            "pr_auc": _safe_pr_auc(validation_frame["target"].to_numpy(), validation_prob),
        }
        fitted[kind] = (model, calibrator)

    best_brier = min(result["brier"] for result in comparison.values())
    near_ties = [
        kind for kind, result in comparison.items()
        if result["brier"] <= best_brier + 0.0001
    ]
    # Prefer the better ranking metric when calibration error is practically
    # tied; this keeps contribution-based explanations available from XGBoost
    # without hiding a meaningful RF win.
    selected_kind = max(near_ties, key=lambda kind: comparison[kind]["pr_auc"])
    model, calibrator = fitted[selected_kind]
    val_prob = _calibrated_probability(model, calibrator, validation_frame)
    cutoff = _threshold(val_prob, validation_frame["target"].to_numpy())
    test_prob = _calibrated_probability(model, calibrator, test_frame)
    baseline = np.clip(test_frame["forecast_rain_prob_6h"].to_numpy() / 100.0, 0.0, 1.0)
    metrics = evaluate(model, calibrator, test_frame, baseline, cutoff)
    city_metrics = {}
    for city_id, city_frame in test_frame.groupby("city_id"):
        city_metrics[str(city_id)] = evaluate(
            model, calibrator, city_frame,
            np.clip(city_frame["forecast_rain_prob_6h"].to_numpy() / 100.0, 0.0, 1.0),
            cutoff,
        )

    without_enso = [column for column in FEATURE_COLUMNS if column not in {"enso_anom", "enso_state_code"}]
    ablation_model = _fit_model(selected_kind, train_frame[without_enso], train_frame["target"], without_enso)
    ablation_calibrator = _fit_isotonic(ablation_model, validation_frame[without_enso + ["target"]], without_enso)
    ablation_prob = _calibrated_probability(ablation_model, ablation_calibrator, test_frame[without_enso + ["target"]], without_enso)
    metrics["ablation_without_enso"] = {
        "brier": float(brier_score_loss(test_frame["target"], ablation_prob)),
        "pr_auc": _safe_pr_auc(test_frame["target"].to_numpy(), ablation_prob),
    }

    artifact = {
        "version": 2,
        "model": model,
        "calibrator": calibrator,
        "feature_names": FEATURE_COLUMNS,
        "model_kind": selected_kind,
        "threshold_mm": threshold_mm,
        "cutoff": cutoff,
        "metadata": {"comparison": comparison, "test": metrics, "city_metrics": city_metrics},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output_path, compress=3)
    report = write_report(frame, train_frame, validation_frame, test_frame, comparison, metrics, city_metrics, threshold_mm, selected_kind, output_path)
    return report


def write_report(frame, train_frame, validation_frame, test_frame, comparison, metrics, city_metrics, threshold_mm, selected_kind, output_path) -> dict[str, Any]:
    base_rate = float(frame["target"].mean())
    rare_note = (
        "The event is rare (<3%). Consider a lower operational threshold (for example 5 mm in 6 hours) "
        "for earlier alerts; do not silently change the configured target."
        if base_rate < 0.03 else "The configured event is not below the 3% rare-event flag."
    )
    report = {
        "base_rate": base_rate, "rows": len(frame), "train_rows": len(train_frame),
        "validation_rows": len(validation_frame), "test_rows": len(test_frame),
        "selected_model": selected_kind, "comparison": comparison, "test": metrics,
        "city_metrics": city_metrics, "threshold_mm": threshold_mm, "artifact": str(output_path),
        "rare_note": rare_note,
    }
    report_path = Path(__file__).with_name("report.md")
    lines = [
        "# Rainfall-risk ML report", "",
        f"**Status:** trained from cached data. Artifact: `backend/models/rainfall_model.joblib`.",
        f"**Target:** rainfall >= {threshold_mm:g} mm in the next 6 hours.",
        f"**Rows:** {len(frame):,}; train {len(train_frame):,}, validation {len(validation_frame):,}, test {len(test_frame):,}.",
        f"**Overall event frequency:** {base_rate:.2%}. {rare_note}", "",
        "## Method",
        "Data is split by calendar time with no shuffling: older years for training, the preceding complete year for validation, and the most recent complete year for testing. Historical Forecast API fields are used when available, with Archive API fallback. Raw data and NOAA ONI text are cached locally.",
        "Features include current/lagged weather, six-hour forecast rain probability/amount, calendar, location/elevation, and monthly ENSO anomaly/state. Future precipitation is used only to form the target.",
        "",
        "## Model comparison (validation)",
        "| Model | Brier | PR-AUC |", "|---|---:|---:|",
    ]
    for name, result in comparison.items():
        lines.append(f"| {name} | {result['brier']:.4f} | {result['pr_auc']:.4f} |")
    lines += ["", f"Selected model: **{selected_kind}**. Probability calibration: isotonic regression fit on validation predictions.",
              "", "## Test metrics", "| Metric | ML | Raw forecast baseline |", "|---|---:|---:|",
              f"| Brier score | {metrics['brier']:.4f} | {metrics['baseline_brier']:.4f} |",
              f"| PR-AUC | {metrics['pr_auc']:.4f} | {metrics['baseline_pr_auc']:.4f} |",
              f"| Precision at {metrics['cutoff']:.2f} | {metrics['precision_at_cutoff']:.4f} | n/a |",
              f"| Recall at {metrics['cutoff']:.2f} | {metrics['recall_at_cutoff']:.4f} | n/a |",
              "", "## ENSO ablation",
              f"With ENSO: Brier {metrics['brier']:.4f}, PR-AUC {metrics['pr_auc']:.4f}.",
              f"Without ENSO: Brier {metrics['ablation_without_enso']['brier']:.4f}, PR-AUC {metrics['ablation_without_enso']['pr_auc']:.4f}.",
              "At a six-hour horizon, ENSO is expected to be weak or neutral as a direct signal; this comparison is retained rather than presenting ENSO as automatically useful.",
              "", "## Calibration curve (test)", "| Mean predicted | Fraction observed |", "|---:|---:|"]
    for point in metrics["calibration"]:
        lines.append(f"| {point['predicted']:.4f} | {point['observed']:.4f} |")
    lines += [
              "", "## Per-city test results", "| City | Rows | Event rate | Brier | PR-AUC | Precision | Recall |", "|---|---:|---:|---:|---:|---:|---:|"]
    for city, result in city_metrics.items():
        lines.append(f"| {city} | {result['rows']} | {result['event_rate']:.2%} | {result['brier']:.4f} | {result['pr_auc']:.4f} | {result['precision_at_cutoff']:.4f} | {result['recall_at_cutoff']:.4f} |")
    lines += ["", "Calibration points are stored in the JSON metadata in the model artifact. Metrics are not a guarantee of operational performance; rerun after each data refresh."]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train calibrated rainfall-risk model.")
    parser.add_argument("--input", type=Path, default=Path("backend/ml/data/raw_weather.sqlite"))
    parser.add_argument("--output", type=Path, default=MODEL_PATH)
    parser.add_argument("--threshold-mm", type=float, default=RAIN_THRESHOLD_MM)
    args = parser.parse_args()
    print(json.dumps(train(args.input, args.output, args.threshold_mm), indent=2, default=str))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
