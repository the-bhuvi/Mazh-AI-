from pydantic import BaseModel, Field
from typing import List, Optional, Union
from datetime import datetime

class Location(BaseModel):
    name: str
    lat: float
    lon: float

class CurrentWeather(BaseModel):
    temp_c: float
    feels_like_c: float
    humidity: int
    pressure_hpa: float
    wind_kph: float
    wind_dir: str
    condition: str

class HourlyWeather(BaseModel):
    time: datetime
    temp_c: float
    rain_prob: int
    rain_mm: float

class DailyWeather(BaseModel):
    date: str
    min_c: float
    max_c: float
    rain_prob: int
    rain_mm: float

class Risk(BaseModel):
    type: str = Field(..., pattern="^(heavy_rain|heat|wind|flood)$")
    score: float = Field(..., ge=0, le=1)
    level: str = Field(..., pattern="^(low|moderate|high)$")
    window: dict # {"start": ISO8601, "end": ISO8601}
    confidence: float
    reasons: List[str]

class Insight(BaseModel):
    summary: str
    recommendations: List[str]
    sms_text: str

class ClimateMeta(BaseModel):
    enso_state: str = Field(..., pattern="^(el_nino|la_nina|neutral|unknown)$")
    nino34_anom: Optional[float]

class Meta(BaseModel):
    sources: List[str]
    ml_used: bool
    fallback_used: bool
    climate: ClimateMeta

class WeatherInsightResponse(BaseModel):
    location: Location
    generated_at: datetime
    current: CurrentWeather
    hourly: List[HourlyWeather]
    daily: List[DailyWeather]
    risks: List[Risk]
    insight: Insight
    meta: Meta
