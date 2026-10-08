import { CloudRain, Droplets, Gauge, MapPin, Sun, Wind } from "lucide-react";
import type { CSSProperties } from "react";
import type { Insight, Risk } from "../types/insight";

const riskLabel = (risk: Risk) => risk.type.replace("_", " ");
const levelClass = (level: string) => `level-${level}`;

export function CurrentWeather({ insight }: { insight: Insight }) {
  const current = insight.current;
  return <section className="current-weather card">
    <div className="section-heading"><div><p className="eyebrow">NOW IN</p><h2><MapPin size={17} /> {insight.location.name}</h2></div><span className="condition-icon"><CloudRain /></span></div>
    <div className="temperature"><strong>{Math.round(current.temp_c)}°</strong><div><span>{current.condition}</span><small>Feels like {Math.round(current.feels_like_c)}°</small></div></div>
    <div className="weather-stats"><span><Droplets /> {current.humidity}% humidity</span><span><Wind /> {current.wind_kph} km/h {current.wind_dir}</span><span><Gauge /> {Math.round(current.pressure_hpa)} hPa</span></div>
  </section>;
}

export function HourlyForecast({ insight }: { insight: Insight }) {
  return <section className="card"><div className="section-heading"><div><p className="eyebrow">NEXT 24 HOURS</p><h2>Rain at a glance</h2></div><CloudRain className="muted-icon" /></div><div className="forecast-scroll">
    {insight.hourly.slice(0, 24).map((hour) => <div className="hour" key={hour.time}><span>{new Date(hour.time).toLocaleTimeString([], { hour: "numeric" })}</span><CloudRain size={18} /><b>{hour.rain_prob}%</b><small>{hour.temp_c.toFixed(0)}°</small></div>)}
  </div></section>;
}

export function DailyForecast({ insight }: { insight: Insight }) {
  return <section className="card"><div className="section-heading"><div><p className="eyebrow">THE WEEK AHEAD</p><h2>Daily rainfall risk</h2></div><Sun className="muted-icon" /></div><div className="daily-list">
    {insight.daily.slice(0, 7).map((day, index) => <div className="daily-row" key={day.date}><strong>{index === 0 ? "Today" : new Date(`${day.date}T12:00:00`).toLocaleDateString([], { weekday: "short" })}</strong><span className="rain-pill"><CloudRain size={15} /> {day.rain_prob}%</span><span className="rain-bar"><i style={{ width: `${day.rain_prob}%` }} /></span><span>{day.min_c}° / <b>{day.max_c}°</b></span></div>)}
  </div></section>;
}

export function RiskGauge({ risk }: { risk: Risk }) {
  const score = Math.max(0, Math.min(1, risk.score));
  return <div className="risk-gauge" aria-label={`${risk.level} risk, ${Math.round(score * 100)} percent`}><div className="gauge-ring" style={{ "--score": `${score * 100}%` } as CSSProperties}><div><strong>{Math.round(score * 100)}%</strong><span>{riskLabel(risk)}</span></div></div><span className={`risk-level ${levelClass(risk.level)}`}>{risk.level}</span></div>;
}

export function RiskReasons({ risks }: { risks: Risk[] }) {
  return <section className="card"><div className="section-heading"><div><p className="eyebrow">UNDERSTAND THE SIGNAL</p><h2>Why?</h2></div></div><div className="reason-list">{risks.flatMap((risk) => risk.reasons.map((reason) => <div className="reason" key={`${risk.type}-${reason}`}><span className={`dot ${levelClass(risk.level)}`} /><div><b>{reason}</b><small>{risk.confidence >= 0.7 ? "Strong signal" : "Useful signal"}</small></div></div>))}</div></section>;
}

export function AlertBanner({ risks }: { risks: Risk[] }) {
  const highRisk = risks.find((risk) => risk.level === "high");
  if (!highRisk) return null;
  return <div className="alert-banner"><CloudRain /><div><strong>Take care: {riskLabel(highRisk)} risk is high</strong><span>{highRisk.reasons[0] || "Plan ahead and stay alert."}</span></div></div>;
}

export function InsightCard({ insight }: { insight: Insight }) {
  return <section className="card insight-card"><p className="eyebrow">RAINWISE SAYS</p><h2>{insight.insight.summary}</h2><div className="recommendations">{insight.insight.recommendations.map((item) => <div key={item}><span>✓</span>{item}</div>)}</div></section>;
}

export function ClimateBadge({ insight }: { insight: Insight }) {
  const label = insight.meta.climate.enso_state.replace("_", " ");
  return <span className="climate-badge" title="seasonal climate context, not a forecast">Climate context: <b>{label}</b></span>;
}

export function Dashboard({ insight }: { insight: Insight }) {
  const mainRisk = [...insight.risks].sort((a, b) => b.score - a.score)[0];
  return <main className="dashboard"><AlertBanner risks={insight.risks} /><div className="location-line"><ClimateBadge insight={insight} /><span>Updated {new Date(insight.generated_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span></div><CurrentWeather insight={insight} />{(insight.meta.fallback_used || !insight.meta.ml_used) && <div className="standard-notice">Showing the standard forecast</div>}<section className="risk-overview card"><div><p className="eyebrow">RAINFALL RISK</p><h2>Your risk signal</h2><p className="muted">A simple score based on the next few hours.</p></div>{mainRisk ? <RiskGauge risk={mainRisk} /> : <span>No active risk</span>}</section><HourlyForecast insight={insight} /><DailyForecast insight={insight} /><div className="two-column"><RiskReasons risks={insight.risks} /><InsightCard insight={insight} /></div></main>;
}
