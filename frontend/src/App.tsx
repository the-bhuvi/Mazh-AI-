import { useEffect, useState } from "react";
import { getWeather } from "./api/client";
import type { WeatherQuery } from "./api/client";
import { ChatWidget } from "./components/ChatWidget";
import { Dashboard } from "./components/Dashboard";
import { LocationPicker } from "./components/LocationPicker";
import { PhoneCard } from "./components/PhoneCard";
import { useGeolocation } from "./hooks/useGeolocation";
import type { Insight } from "./types/insight";

function Skeleton() {
  return <div className="dashboard skeleton-dashboard"><div className="skeleton hero-skeleton" /><div className="skeleton" /><div className="skeleton wide" /><div className="skeleton" /></div>;
}

export default function App() {
  const location = useGeolocation();
  const [insight, setInsight] = useState<Insight>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (location.status === "loading" || location.status === "idle") return;
    if (location.lat !== undefined && location.lon !== undefined) {
      setLoading(true); setError("");
      getWeather({ lat: location.lat, lon: location.lon }).then(setInsight).catch((err) => setError(err instanceof Error ? err.message : "We could not load your weather.")).finally(() => setLoading(false));
    } else setLoading(false);
  }, [location.status, location.lat, location.lon]);

  async function chooseLocation(query: WeatherQuery) {
    setLoading(true); setError("");
    try { setInsight(await getWeather(query)); } catch (err) { setError(err instanceof Error ? err.message : "We could not load that location."); } finally { setLoading(false); }
  }

  return <div className="app-shell"><header className="topbar"><a className="brand" href="/"><span className="brand-mark">☔</span><span>rainwise</span></a><span className="tagline">Rainfall risk, made clear.</span></header><div className="page-intro"><p className="eyebrow">CLIMATE INTELLIGENCE</p><h1>Plan your day<br /><em>with confidence.</em></h1><p>Understand rainfall risk in plain language, wherever you are.</p></div>{(location.status === "denied" || location.status === "unavailable") && !insight && <LocationPicker onSelect={chooseLocation} />}{loading && <Skeleton />}{error && !loading && <div className="error-state"><h2>We could not reach the weather service</h2><p>{error}</p><button className="button primary" onClick={() => window.location.reload()}>Try again</button></div>}{insight && !loading && <><Dashboard insight={insight} /><div className="support-grid"><ChatWidget insight={insight} /><PhoneCard insight={insight} /></div></>}<footer>Rainwise gives practical guidance from forecast data. Climate context is not a forecast.</footer></div>;
}
