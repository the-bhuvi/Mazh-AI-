import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root or backend directory if present
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'cache.db'}").replace("sqlite:///", "")

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
ENV = os.getenv("ENV", "development")

# LLM Configuration
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("GEMINI_API_KEY", ""))

# Twilio Credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
VOICE_STATE_SECRET = os.getenv("VOICE_STATE_SECRET", TWILIO_AUTH_TOKEN or "development-voice-secret")
VOICE_BASE_URL = os.getenv("VOICE_BASE_URL", "")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "")
TTS_API_URL = os.getenv("TTS_API_URL", "")
TTS_API_KEY = os.getenv("TTS_API_KEY", "")
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-IN")
TTS_VOICE_TA = os.getenv("TTS_VOICE_TA", "ta-IN")
VOICE_AUDIO_DIR = BASE_DIR / "backend" / "voice_audio"
VOICE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VOICE_AUDIO_PUBLIC_URL = os.getenv("VOICE_AUDIO_PUBLIC_URL", "")
PHONE_API_KEY = os.getenv("PHONE_API_KEY", "")

# CORS origins
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "https://mazh-ai.vercel.app,http://localhost:5173,http://localhost:3000",
    ).split(",")
    if origin.strip()
]

CITIES_FILE = CONFIG_DIR / "cities.json"
ML_COVERAGE_FILE = CONFIG_DIR / "ml_coverage.json"
MODEL_PATH = BASE_DIR / "backend" / "models" / "rainfall_model.joblib"
ML_ENABLED = os.getenv("ML_ENABLED", "true").lower() == "true"
RAIN_THRESHOLD_MM = float(os.getenv("RAIN_THRESHOLD_MM", "10"))
ML_DATA_DIR = BASE_DIR / "backend" / "ml" / "data"
ML_DATA_DIR.mkdir(parents=True, exist_ok=True)
