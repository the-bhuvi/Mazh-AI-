from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class LocationSchema(BaseModel):
    name: str
    lat: float
    lon: float

class CurrentWeatherSchema(BaseModel):
    temp_c: float
    feels_like_c: float
    humidity: int
    pressure_hpa: float
    wind_kph: float
    wind_dir: str
    condition: str

class HourlyForecastSchema(BaseModel):
    time: str
    temp_c: float
    rain_prob: int
    rain_mm: float

class DailyForecastSchema(BaseModel):
    date: str
    min_c: float
    max_c: float
    rain_prob: int
    rain_mm: float

class RiskWindowSchema(BaseModel):
    start: str
    end: str

class RiskSchema(BaseModel):
    type: Literal["heavy_rain", "heat", "wind", "flood"]
    score: float = Field(ge=0.0, le=1.0)
    level: Literal["low", "moderate", "high"]
    window: RiskWindowSchema
    confidence: float
    reasons: List[str]

class InsightContentSchema(BaseModel):
    summary: str
    recommendations: List[str]
    sms_text: str

class ClimateSchema(BaseModel):
    enso_state: Literal["el_nino", "la_nina", "neutral", "unknown"]
    nino34_anom: Optional[float] = None

class MetaSchema(BaseModel):
    sources: List[str]
    ml_used: bool
    fallback_used: bool
    climate: ClimateSchema

class InsightSchema(BaseModel):
    location: LocationSchema
    generated_at: str
    current: CurrentWeatherSchema
    hourly: List[HourlyForecastSchema]
    daily: List[DailyForecastSchema]
    risks: List[RiskSchema]
    insight: InsightContentSchema
    meta: MetaSchema

# Request & Response DTOs
class PredictRequest(BaseModel):
    lat: float
    lon: float

class PredictResponse(BaseModel):
    score: float
    level: Literal["low", "moderate", "high"]
    reasons: List[str]
    risks: List[RiskSchema]

class ChatRequest(BaseModel):
    session_id: str
    message: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    place: Optional[str] = None
    pin: Optional[str] = None
    lang: Optional[str] = "en"

class ChatResponse(BaseModel):
    reply: str
    intent: str
    insight: Optional[InsightSchema] = None

class SmsRequest(BaseModel):
    phone: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    pin: Optional[str] = None
    place: Optional[str] = None

class SmsResponse(BaseModel):
    status: str
    detail: Optional[str] = None
