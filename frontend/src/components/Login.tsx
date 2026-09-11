import React, { useState } from "react";
import { Link } from "react-router-dom";
import { login, saveToken } from "../api/auth";

type Props = {
  onLogin: () => void;
};

export default function Login({ onLogin }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const token = await login(email, password);
      saveToken(token.access_token);
      onLogin();
    } catch (err: any) {
      setError(err?.message ?? "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        maxWidth: 400,
        margin: "4rem auto",
        padding: 28,
        background: "white",
        borderRadius: 12,
        boxShadow: "0 4px 16px rgba(0,0,0,0.06)",
      }}
    >
      <div style={{ textAlign: "center", marginBottom: 24 }}>
        <h2 style={{ margin: "0 0 6px", fontSize: "1.6rem", color: "#111827" }}>
          Welcome Back
        </h2>
        <p style={{ margin: 0, fontSize: "0.9rem", color: "#6b7280" }}>
          Log in to access your inventory homes
        </p>
      </div>

      <form
        onSubmit={submit}
        style={{ display: "flex", flexDirection: "column", gap: 16 }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label
            style={{ fontSize: "0.9rem", fontWeight: 500, color: "#374151" }}
          >
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="you@example.com"
            style={{
              padding: 10,
              borderRadius: 6,
              border: "1px solid #d1d5db",
              fontSize: "0.95rem",
            }}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label
            style={{ fontSize: "0.9rem", fontWeight: 500, color: "#374151" }}
          >
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="••••••••"
            style={{
              padding: 10,
              borderRadius: 6,
              border: "1px solid #d1d5db",
              fontSize: "0.95rem",
            }}
          />
        </div>

        {error && (
          <div
            style={{
              color: "#dc2626",
              background: "#fef2f2",
              padding: 10,
              borderRadius: 6,
              textAlign: "center",
              fontSize: "0.9rem",
              fontWeight: 500,
            }}
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            background: "#2563eb",
            color: "white",
            border: "none",
            padding: "12px",
            borderRadius: 6,
            fontWeight: 600,
            fontSize: "1rem",
            cursor: "pointer",
            marginTop: 4,
          }}
        >
          {loading ? "Logging in..." : "Log in"}
        </button>

        <p
          style={{
            textAlign: "center",
            fontSize: "0.9rem",
            color: "#4b5563",
            marginTop: 8,
          }}
        >
          New here?{" "}
          <Link
            to="/register"
            style={{
              color: "#2563eb",
              textDecoration: "none",
              fontWeight: 500,
            }}
          >
            Create an account
          </Link>
        </p>
      </form>
    </div>
  );
}
