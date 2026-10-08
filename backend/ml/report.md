# Rainfall-risk ML report

**Status:** trained from cached data. Artifact: `backend/models/rainfall_model.joblib`.
**Target:** rainfall >= 10 mm in the next 6 hours.
**Rows:** 560,928; train 420,624, validation 70,272, test 70,032.
**Overall event frequency:** 1.97%. The event is rare (<3%). Consider a lower operational threshold (for example 5 mm in 6 hours) for earlier alerts; do not silently change the configured target.

## Method
Data is split by calendar time with no shuffling: older years for training, the preceding complete year for validation, and the most recent complete year for testing. Historical Forecast API fields are used when available, with Archive API fallback. Raw data and NOAA ONI text are cached locally.
Features include current/lagged weather, six-hour forecast rain probability/amount, calendar, location/elevation, and monthly ENSO anomaly/state. Future precipitation is used only to form the target.

## Model comparison (validation)
| Model | Brier | PR-AUC |
|---|---:|---:|
| xgboost | 0.0219 | 0.2333 |
| random_forest | 0.0219 | 0.2316 |

Selected model: **xgboost**. Probability calibration: isotonic regression fit on validation predictions.

## Test metrics
| Metric | ML | Raw forecast baseline |
|---|---:|---:|
| Brier score | 0.0175 | 0.1210 |
| PR-AUC | 0.2460 | 0.1388 |
| Precision at 0.30 | 0.5053 | n/a |
| Recall at 0.30 | 0.1321 | n/a |

## ENSO ablation
With ENSO: Brier 0.0175, PR-AUC 0.2460.
Without ENSO: Brier 0.0175, PR-AUC 0.2508.
At a six-hour horizon, ENSO is expected to be weak or neutral as a direct signal; this comparison is retained rather than presenting ENSO as automatically useful.

## Calibration curve (test)
| Mean predicted | Fraction observed |
|---:|---:|
| 0.0000 | 0.0010 |
| 0.0007 | 0.0013 |
| 0.0012 | 0.0014 |
| 0.0044 | 0.0021 |
| 0.0078 | 0.0049 |
| 0.0155 | 0.0163 |
| 0.0276 | 0.0221 |
| 0.0353 | 0.0351 |
| 0.1444 | 0.1363 |

## Per-city test results
| City | Rows | Event rate | Brier | PR-AUC | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| chennai | 8754 | 3.08% | 0.0232 | 0.3784 | 0.6489 | 0.2259 |
| coimbatore | 8754 | 1.66% | 0.0161 | 0.0987 | 0.2162 | 0.0552 |
| cuddalore | 8754 | 2.60% | 0.0204 | 0.3477 | 0.6557 | 0.1754 |
| madurai | 8754 | 1.56% | 0.0147 | 0.1195 | 0.3182 | 0.0511 |
| ooty | 8754 | 2.40% | 0.0194 | 0.2937 | 0.4318 | 0.1810 |
| salem | 8754 | 1.56% | 0.0144 | 0.1203 | 0.0000 | 0.0000 |
| thoothukudi | 8754 | 1.84% | 0.0155 | 0.2422 | 0.4722 | 0.1056 |
| tiruchirappalli | 8754 | 1.88% | 0.0165 | 0.2060 | 0.5385 | 0.1273 |

The same calibration points are stored in the JSON metadata in the model artifact. Metrics are not a guarantee of operational performance; rerun after each data refresh.
