import { Send, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";
import { sendChat } from "../api/client";
import type { Insight } from "../types/insight";

type Message = { from: "user" | "bot"; text: string };

export function ChatWidget({ insight }: { insight: Insight }) {
  const [messages, setMessages] = useState<Message[]>([{ from: "bot", text: "Ask me about rain risk, timing, or what to do next." }]);
  const [message, setMessage] = useState("");
  const [lang, setLang] = useState<"en" | "ta">("en");
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState(() => crypto.randomUUID());

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!text || loading) return;
    setMessage("");
    setMessages((current) => [...current, { from: "user", text }]);
    setLoading(true);
    try {
      const response = await sendChat({ session_id: sessionId, message: text, lat: insight.location.lat, lon: insight.location.lon, lang });
      setMessages((current) => [...current, { from: "bot", text: response.reply }]);
    } catch (error) {
      setMessages((current) => [...current, { from: "bot", text: error instanceof Error ? error.message : "I could not answer that right now." }]);
    } finally { setLoading(false); }
  }

  return <section className="card chat-widget"><div className="section-heading"><div><p className="eyebrow">RAINWISE CHAT</p><h2><Sparkles size={18} /> Ask about your day</h2></div><div className="language-toggle"><button className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>English</button><button className={lang === "ta" ? "active" : ""} onClick={() => setLang("ta")}>தமிழ்</button></div></div><div className="messages" aria-live="polite">{messages.map((item, index) => <div className={`message ${item.from}`} key={`${item.text}-${index}`}>{item.text}</div>)}{loading && <div className="message bot typing">Thinking…</div>}</div><form className="chat-form" onSubmit={submit}><input value={message} onChange={(event) => setMessage(event.target.value)} placeholder={lang === "ta" ? "மழை பற்றி கேளுங்கள்..." : "Will it rain today?"} aria-label="Chat message" /><button type="submit" aria-label="Send message" disabled={loading || !message.trim()}><Send size={17} /></button></form></section>;
}
