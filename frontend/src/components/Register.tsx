import React, { useState } from "react";
import { Link } from "react-router-dom";
import { register } from "../api/auth";

export default function Register() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [submittedEmail, setSubmittedEmail] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    const name = username.trim();
    if (name.length < 3 || name.length > 50) {
      setError("Username must contain 3 to 50 characters.");
      return;
    }
    setPending(true);
    setError("");
    try {
      await register(name, email.trim());
      setSubmittedEmail(email.trim());
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Registration failed. Please try again.",
      );
    } finally {
      setPending(false);
    }
  }

  if (submittedEmail) {
    return (
      <section style={{ maxWidth: 400, margin: "24px auto" }}>
        <h2>Check your email</h2>
        <p role="status">
          An activation email has been queued for {submittedEmail}.
        </p>
        <p>
          Delivery may take a moment. Follow the link to choose your password
          and activate your account. Check your spam folder too.
        </p>
        <Link to="/login">Back to login</Link>
      </section>
    );
  }

  return (
    <form
      onSubmit={submit}
      style={{ maxWidth: 400, margin: "24px auto", display: "grid", gap: 12 }}
    >
      <h2>Create an account</h2>
      <p>
        We’ll email you a link to set your password and activate your account.
      </p>
      <label htmlFor="register-username">Username</label>
      <input
        id="register-username"
        name="username"
        autoComplete="username"
        required
        minLength={3}
        maxLength={50}
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        disabled={pending}
      />
      <label htmlFor="register-email">Email</label>
      <input
        id="register-email"
        name="email"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        disabled={pending}
      />
      {error && (
        <p role="alert" style={{ color: "#b00020" }}>
          {error}
        </p>
      )}
      <button type="submit" disabled={pending}>
        {pending ? "Registering…" : "Create account"}
      </button>
      <p>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </form>
  );
}
