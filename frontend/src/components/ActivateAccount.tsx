import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { API_BASE } from "../api/auth";

export default function ActivateAccount() {
  const { key } = useParams<{ key: string }>();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!key || pending) return;
    if (password !== confirmation) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 6 || !/\d/.test(password)) {
      setError("Use at least 6 characters and include a number.");
      return;
    }
    setError("");
    setPending(true);
    try {
      const response = await fetch(
        `${API_BASE}/users/activate/${encodeURIComponent(key)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password, confirm_password: confirmation }),
        },
      );
      const body = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : "Activation failed. Please check your details or request a new link.",
        );
      setPassword("");
      setConfirmation("");
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation failed.");
    } finally {
      setPending(false);
    }
  }

  if (!key) return <p>The activation link is missing its key.</p>;
  if (done)
    return (
      <p>
        Your account is active. <Link to="/login">Log in</Link>
      </p>
    );
  return (
    <form onSubmit={submit} style={{ maxWidth: 360, margin: "24px auto" }}>
      <h2>Activate your account</h2>
      <p>Choose a password with at least 6 characters and a number.</p>
      <label>
        Password{" "}
        <input
          type="password"
          autoComplete="new-password"
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label>
        Confirm password{" "}
        <input
          type="password"
          autoComplete="new-password"
          required
          minLength={6}
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
        />
      </label>
      {error && <p role="alert">{error}</p>}
      <button disabled={pending}>
        {pending ? "Activating…" : "Activate account"}
      </button>
    </form>
  );
}
