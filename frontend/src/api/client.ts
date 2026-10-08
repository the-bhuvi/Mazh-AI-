import type { Insight, Location, Risk } from "../types/insight";

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const TIMEOUT_MS = 10_000;

export type WeatherQuery =
  | { lat: number; lon: number }
  | { place: string }
  | { pin: string };

export interface ChatResponse {
  reply: string;
  intent: string;
  insight?: Insight;
}

export interface SmsResponse {
  status: string;
}

export interface ChatRequest {
  session_id: string;
  message: string;
  lat?: number;
  lon?: number;
  lang: "en" | "ta";
}

export interface SmsRequest {
  phone: string;
  lat?: number;
  lon?: number;
  pin?: string;
  place?: string;
}

function isMock() {
  return import.meta.env.VITE_USE_MOCK === "true";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_URL) throw new Error("The weather service URL is not configured.");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Weather service returned ${response.status}.`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("The weather service took too long to respond.");
    }
    throw error instanceof Error ? error : new Error("Unable to contact the weather service.");
  } finally {
    window.clearTimeout(timeout);
  }
}

const mockInsight: Insight = {
  location: { name: "Chennai", lat: 13.0827, lon: 80.2707 },
  generated_at: "2026-10-08T08:00:00.000Z",
  current: {
    temp_c: 29.4, feels_like_c: 33.2, humidity: 78, pressure_hpa: 1008.4,
    wind_kph: 14, wind_dir: "SW", condition: "Partly cloudy",
  },
  hourly: Array.from({ length: 24 }, (_, index) => ({
    time: new Date(Date.now() + index * 3600000).toISOString(),
    temp_c: Math.round((29 + Math.sin(index / 4) * 2) * 10) / 10,
    rain_prob: Math.min(90, Math.max(8, 25 + index * 2)),
    rain_mm: index > 4 && index < 11 ? 1.2 : 0,
  })),
  daily: Array.from({ length: 7 }, (_, index) => ({
    date: new Date(Date.now() + index * 86400000).toISOString().slice(0, 10),
    min_c: 25 + (index % 2), max_c: 33 + (index % 3),
    rain_prob: [65, 72, 48, 30, 25, 35, 42][index],
    rain_mm: [12, 18, 5, 1, 0, 2, 4][index],
  })),
  risks: [{
    type: "heavy_rain", score: 0.68, level: "moderate",
    window: { start: "2026-10-08T13:00:00.000Z", end: "2026-10-08T20:00:00.000Z" },
    confidence: 0.82,
    reasons: ["Rain is most likely this afternoon", "Moist air is building over the coast"],
  }],
  insight: {
    summary: "Keep a rain plan ready this afternoon. Showers may be brief but locally heavy.",
    recommendations: ["Carry an umbrella after lunch", "Allow extra travel time between 2–7 PM", "Keep low-lying areas in mind if rain persists"],
    sms_text: "Rainwise: Moderate rain risk this afternoon in Chennai. Carry an umbrella and allow extra travel time.",
  },
  meta: { sources: ["standard forecast", "climate context"], ml_used: true, fallback_used: false,
    climate: { enso_state: "el_nino", nino34_anom: 0.8 } },
};

export function getMockInsight(): Insight {
  return { ...mockInsight, location: { ...mockInsight.location } };
}

export async function getWeather(query: WeatherQuery): Promise<Insight> {
  if (isMock()) return getMockInsight();
  const params = new URLSearchParams();
  if ("lat" in query) { params.set("lat", String(query.lat)); params.set("lon", String(query.lon)); }
  if ("place" in query) params.set("place", query.place);
  if ("pin" in query) params.set("pin", query.pin);
  return request<Insight>(`/weather?${params.toString()}`);
}

export async function sendChat(body: ChatRequest): Promise<ChatResponse> {
  if (isMock()) return {
    reply: body.lang === "ta"
      ? "இன்று பிற்பகலில் மழை வாய்ப்பு உள்ளது. குடையை எடுத்துச் செல்லுங்கள்."
      : "Rain is most likely this afternoon. Carry an umbrella and allow extra travel time.",
    intent: "rainfall_risk",
  };
  return request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(body) });
}

export async function sendSms(body: SmsRequest): Promise<SmsResponse> {
  if (isMock()) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    return { status: "sent" };
  }
  return request<SmsResponse>("/sms", { method: "POST", body: JSON.stringify(body) });
}

export type { Insight, Location, Risk };
