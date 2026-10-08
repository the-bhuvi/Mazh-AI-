import sys
import logging
import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import GradientBoostingClassifier

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import MODEL_PATH

logger = logging.getLogger(__name__)

def train_and_save_model():
    """
    Trains a calibrated Gradient Boosting Classifier on rainfall risk features
    and saves the model artifact to models/rainfall_model.joblib.
    """
    np.random.seed(42)
    n_samples = 1500

    # Feature definitions:
    # 0: max_rain_24h_mm (0 - 150 mm)
    # 1: max_rain_prob (0 - 100 %)
    # 2: peak_3h_rain_mm (0 - 80 mm)
    # 3: humidity (30 - 100 %)
    # 4: pressure_drop_hpa (0 - 20 hPa)
    # 5: wind_speed_kph (0 - 60 kph)
    # 6: el_nino_anom (-2.0 to +3.0 °C)

    max_rain = np.random.uniform(0, 150, n_samples)
    rain_prob = np.random.uniform(0, 100, n_samples)
    peak_3h = np.random.uniform(0, 80, n_samples)
    humidity = np.random.uniform(40, 100, n_samples)
    press_drop = np.random.uniform(0, 25, n_samples)
    wind_spd = np.random.uniform(5, 60, n_samples)
    nino_anom = np.random.uniform(-1.5, 2.5, n_samples)

    X = np.column_stack([max_rain, rain_prob, peak_3h, humidity, press_drop, wind_spd, nino_anom])

    # Target risk score calculation logic for training set ground truth
    # 0: low (<0.35), 1: moderate (0.35 - 0.70), 2: high (>0.70)
    scores = (
        (max_rain / 120.0) * 0.40 +
        (rain_prob / 100.0) * 0.25 +
        (peak_3h / 60.0) * 0.20 +
        (np.maximum(0, nino_anom) / 2.0) * 0.15
    )
    # Add minor noise
    scores += np.random.normal(0, 0.05, n_samples)
    scores = np.clip(scores, 0.0, 1.0)

    y = np.where(scores >= 0.70, 2, np.where(scores >= 0.35, 1, 0))

    clf = GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)
    clf.fit(X, y)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    logger.info(f"Rainfall ML model successfully trained and saved to {MODEL_PATH}")
    print(f"Model saved to {MODEL_PATH}")

if __name__ == "__main__":
    train_and_save_model()
