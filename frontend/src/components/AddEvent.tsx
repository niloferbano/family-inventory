import React, { useState } from "react";
import { createEvent } from "../api/events";
import { clearToken } from "../api/auth";

export default function AddEvent({ onLogout }: { onLogout: () => void }) {
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await createEvent({
        subject,
        message,
        source: "ui",
      });
      setResult(`Created event ${res.event_id}`);
      setSubject("");
      setMessage("");
    } catch (err: any) {
      // if unauthorized, prompt logout
      if (String(err).includes("401") || String(err).toLowerCase().includes("unauthorized")) {
        clearToken();
        onLogout();
        return;
      }
      setError(err?.message ?? "Failed to create event");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 640, margin: "1rem auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
        <h3>Create Notification Event</h3>
        <button onClick={() => { clearToken(); onLogout(); }}>Logout</button>
      </div>

      <form onSubmit={submit}>
        <div>
          <label>Subject</label>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} required />
        </div>
        <div>
          <label>Message</label>
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} required rows={4} />
        </div>
        <div style={{ marginTop: 12 }}>
          <button type="submit" disabled={loading}>{loading ? "Creating…" : "Create Event"}</button>
        </div>
        {result && <div style={{ color: "green", marginTop: 8 }}>{result}</div>}
        {error && <div style={{ color: "crimson", marginTop: 8 }}>{error}</div>}
      </form>
    </div>
  );
}