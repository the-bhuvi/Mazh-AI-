export type RiskType = "heavy_rain" | "heat" | "wind" | "flood";
export type RiskLevel = "low" | "moderate" | "high";
export type EnsoState = "el_nino" | "la_nina" | "neutral" | "unknown";

export interface Location {
  name: string;
  lat: number;
  lon: number;
}

export interface CurrentWeather {
  temp_c: number;
  feels_like_c: number;
  humidity: number;
  pressure_hpa: number;
  wind_kph: number;
  wind_dir: string;
  condition: string;
}

export interface HourlyForecast {
  time: string;
  temp_c: number;
  rain_prob: number;
  rain_mm: number;
}

export interface DailyForecast {
  date: string;
  min_c: number;
  max_c: number;
  rain_prob: number;
  rain_mm: number;
}

export interface Risk {
  type: RiskType;
  score: number;
  level: RiskLevel;
  window: {
    start: string;
    end: string;
  };
  confidence: number;
  reasons: string[];
}

export interface InsightSummary {
  summary: string;
  recommendations: string[];
  sms_text: string;
}

export interface Climate {
  enso_state: EnsoState;
  nino34_anom: number | null;
}

export interface InsightMeta {
  sources: string[];
  ml_used: boolean;
  fallback_used: boolean;
  climate: Climate;
}

export interface Insight {
  location: Location;
  generated_at: string;
  current: CurrentWeather;
  hourly: HourlyForecast[];
  daily: DailyForecast[];
  risks: Risk[];
  insight: InsightSummary;
  meta: InsightMeta;
}
