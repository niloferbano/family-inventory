import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { requestPasswordReset, resetPassword } from "../api/auth";

export default function PasswordReset({ confirm = false }: { confirm?: boolean }) {
  const { token } = useParams<{ token: string }>();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    setError("");
    if (confirm) {
      if (!token) { setError("This reset link is incomplete. Request a new link."); return; }
      if (password !== confirmation) { setError("Passwords do not match."); return; }
      if (password.length < 6 || !/\d/.test(password)) {
        setError("Use at least 6 characters and include a number."); return;
      }
      if (new TextEncoder().encode(password).length > 72) {
        setError("Your password is too long. Please use a shorter password."); return;
      }
    }
    setPending(true);
    try {
      if (confirm && token) await resetPassword(token, password, confirmation);
      else await requestPasswordReset(email.trim());
      setPassword("");
      setConfirmation("");
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally { setPending(false); }
  }

  const inputStyle: React.CSSProperties = { display: "block", width: "100%", boxSizing: "border-box", padding: 10, marginTop: 6, border: "1px solid #d1d5db", borderRadius: 6 };
  return (
    <section style={{ maxWidth: 400, margin: "4rem auto", padding: 28, background: "white", borderRadius: 12, boxShadow: "0 4px 16px rgba(0,0,0,0.06)" }}>
      <h2>{confirm ? "Reset your password" : "Forgot password?"}</h2>
      {done ? (
        <p role="status">{confirm
          ? "Your password has been reset. You can now log in with your new password."
          : "If an eligible account exists for this email address, a password reset link will be sent. Check your inbox and spam folder."}</p>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <p>{confirm ? "Choose a password with at least 6 characters and a number." : "Enter your email address and we’ll send you a password reset link."}</p>
          {confirm ? <>
            <label>New password<input style={inputStyle} type="password" autoComplete="new-password" required minLength={6} value={password} onChange={e => setPassword(e.target.value)} /></label>
            <label>Confirm password<input style={inputStyle} type="password" autoComplete="new-password" required minLength={6} value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
          </> : <label>Email<input style={inputStyle} type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>}
          {error && <p role="alert" style={{ color: "#dc2626" }}>{error}</p>}
          <button type="submit" disabled={pending || (confirm && !token)} style={{ padding: 12, background: "#2563eb", color: "white", border: 0, borderRadius: 6, cursor: "pointer" }}>
            {pending ? "Please wait…" : confirm ? "Reset password" : "Send reset link"}
          </button>
        </form>
      )}
      {confirm && !done && <p><Link to="/forgot-password">Request a new reset link</Link></p>}
      <p><Link to="/login">Back to login</Link></p>
    </section>
  );
}
