import { Phone, Send } from "lucide-react";
import { FormEvent, useState } from "react";
import { sendSms } from "../api/client";
import type { Insight } from "../types/insight";

export function PhoneCard({ insight }: { insight: Insight }) {
  const phone = import.meta.env.VITE_PHONE_NUMBER || "+91 80000 00000";
  const [number, setNumber] = useState("");
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^\d{10}$/.test(number) || !consent) return;
    setState("loading"); setError("");
    try { await sendSms({ phone: number, lat: insight.location.lat, lon: insight.location.lon }); setState("success"); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not send the SMS."); setState("error"); }
  }

  return <section className="card phone-card"><div className="phone-info"><div className="icon-circle"><Phone /></div><div><p className="eyebrow">NO SMARTPHONE? NO PROBLEM.</p><h2>Get it by phone</h2><a href={`tel:${phone.replace(/\s/g, "")}`}>{phone}</a></div></div><div className="keypad-steps"><span><b>1</b> Choose language</span><span><b>2</b> Enter your PIN + #</span><span><b>3</b> Choose a menu option</span></div><div className="sms-divider"><span>or send it to your phone</span></div><form className="sms-form" onSubmit={submit}><label htmlFor="mobile">Send me this by SMS</label><input id="mobile" inputMode="numeric" maxLength={10} value={number} onChange={(event) => { setNumber(event.target.value.replace(/\D/g, "")); setState("idle"); }} placeholder="10-digit mobile number" /><label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> I agree to receive this one-time message.</label><button className="button primary" disabled={state === "loading" || !/^\d{10}$/.test(number) || !consent}>{state === "loading" ? "Sending…" : <><Send size={16} /> Send SMS</>}</button>{state === "success" && <p className="form-success">Message sent. Check your phone shortly.</p>}{state === "error" && <p className="form-error">{error}</p>}</form></section>;
}
