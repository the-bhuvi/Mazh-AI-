import { useState } from "react";
import type { WeatherQuery } from "../api/client";

const cities = ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli"];

export function LocationPicker({ onSelect }: { onSelect: (query: WeatherQuery) => void }) {
  const [pin, setPin] = useState("");
  const [place, setPlace] = useState("");
  return <section className="location-picker card"><p className="eyebrow">CHOOSE YOUR LOCATION</p><h2>Where should we look?</h2><p className="muted">Use a 6-digit PIN, choose a city, or search by place.</p><div className="location-fields"><form onSubmit={(e) => { e.preventDefault(); if (/^\d{6}$/.test(pin)) onSelect({ pin }); }}><label htmlFor="pin">PIN code</label><div className="inline-input"><input id="pin" inputMode="numeric" maxLength={6} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} placeholder="600001" /><button disabled={!/^\d{6}$/.test(pin)}>Go</button></div></form><label htmlFor="city">Preset city<select id="city" defaultValue="" onChange={(e) => e.target.value && onSelect({ place: e.target.value })}><option value="" disabled>Select a city</option>{cities.map((city) => <option key={city}>{city}</option>)}</select></label><form onSubmit={(e) => { e.preventDefault(); if (place.trim()) onSelect({ place: place.trim() }); }}><label htmlFor="place">Search by place</label><div className="inline-input"><input id="place" value={place} onChange={(e) => setPlace(e.target.value)} placeholder="e.g. Salem" /><button disabled={!place.trim()}>Go</button></div></form></div></section>;
}
