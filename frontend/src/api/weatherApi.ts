/**
 * Open-Meteo Weather API Client
 *
 * Provides typed wrappers for:
 *  - Current / forecast weather  → GET /weather/current (backend proxy)
 *  - Historical weather           → GET /weather/historical (backend proxy)
 *
 * Both endpoints ultimately call Open-Meteo's public APIs:
 *  - Forecast : https://api.open-meteo.com/v1/forecast
 *  - Archive  : https://archive-api.open-meteo.com/v1/archive
 */

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const TIMEOUT_MS = 15_000;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CurrentWeatherData {
  lat: number;
  lon: number;
  current: {
    temp_c: number;
    feels_like_c: number;
    humidity: number;
    pressure_hpa: number;
    wind_kph: number;
    wind_dir: string;
    condition: string;
  };
  hourly: Array<{
    time: string;
    temp_c: number;
    rain_prob: number;
    rain_mm: number;
  }>;
  daily: Array<{
    date: string;
    min_c: number;
    max_c: number;
    rain_prob: number;
    rain_mm: number;
  }>;
}

export interface HistoricalHourly {
  time: string;
  temp_c: number | null;
  precipitation_mm: number;
  humidity: number | null;
  wind_kph: number | null;
  wind_dir: string;
  condition: string;
}

export interface HistoricalDaily {
  date: string;
  min_c: number | null;
  max_c: number | null;
  avg_c: number | null;
  total_precipitation_mm: number;
}

export interface HistoricalWeatherData {
  lat: number;
  lon: number;
  start_date: string;
  end_date: string;
  timezone: string;
  hourly: HistoricalHourly[];
  daily: HistoricalDaily[];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function weatherRequest<T>(path: string): Promise<T> {
  if (!API_URL) throw new Error("VITE_API_URL is not configured.");

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${API_URL}${path}`, { signal: controller.signal });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(
        body?.detail ?? `Weather API error: ${res.status} ${res.statusText}`
      );
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Weather API request timed out.");
    }
    throw err instanceof Error ? err : new Error("Unable to contact weather service.");
  } finally {
    window.clearTimeout(timer);
  }
}

// ─── API Functions ────────────────────────────────────────────────────────────

/**
 * Fetch current + forecast weather for a location.
 *
 * Backend proxies:  https://api.open-meteo.com/v1/forecast?latitude=...&longitude=...
 *
 * @example
 * const data = await getCurrentWeather(52.52, 13.41);
 */
export async function getCurrentWeather(
  lat: number,
  lon: number
): Promise<CurrentWeatherData> {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
  });
  return weatherRequest<CurrentWeatherData>(`/weather/current?${params}`);
}

/**
 * Fetch historical weather data for a date range.
 *
 * Backend proxies:  https://archive-api.open-meteo.com/v1/archive?latitude=...&start_date=...
 *
 * @param lat        Latitude
 * @param lon        Longitude
 * @param startDate  ISO date string, e.g. "2026-09-22"
 * @param endDate    ISO date string, e.g. "2026-10-06"
 *
 * @example
 * const history = await getHistoricalWeather(52.52, 13.41, "2026-09-22", "2026-10-06");
 */
export async function getHistoricalWeather(
  lat: number,
  lon: number,
  startDate: string,
  endDate: string
): Promise<HistoricalWeatherData> {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    start_date: startDate,
    end_date: endDate,
  });
  return weatherRequest<HistoricalWeatherData>(`/weather/historical?${params}`);
}
