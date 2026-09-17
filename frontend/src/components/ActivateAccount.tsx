import React, { useState, useEffect } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { API_BASE } from "../api/auth";

export default function ActivateAccount() {
  const { key } = useParams<{ key: string }>();
  const navigate = useNavigate();
  
  // Password form states
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");

  // Page-load token validation states
  const [isValidating, setIsValidating] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [isAlreadyActive, setIsAlreadyActive] = useState(false);

  // Action states
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  // Inline Resend states
  const [resendEmail, setResendEmail] = useState("");
  const [resendPending, setResendPending] = useState(false);
  const [resendMessage, setResendMessage] = useState("");
  const [resendDone, setResendDone] = useState(false);

  // 1. Verify token on page load (GET)
  useEffect(() => {
    if (!key) {
      setIsValidating(false);
      setTokenValid(false);
      return;
    }

    async function verifyToken() {
      try {
        const response = await fetch(
          `${API_BASE}/users/activate/${encodeURIComponent(key!)}`,
          { method: "GET" }
        );
        
        const body = await response.json().catch(() => ({}));

        if (response.ok) {
          setTokenValid(true);
        } else {
          if (body.detail === "ALREADY_ACTIVE") {
            setIsAlreadyActive(true);
          }
          setTokenValid(false);
        }
      } catch (err) {
        setTokenValid(false);
      } finally {
        setIsValidating(false);
      }
    }

    verifyToken();
  }, [key]);

  // 2. Handle account activation & password creation (POST)
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
        `${API_BASE}/users/activate/${encodeURIComponent(key!)}`,
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

      // Optional: Automatically redirect to login after a short delay (e.g., 3 seconds)
      setTimeout(() => {
        navigate("/login");
      }, 3000);

    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation failed.");
    } finally {
      setPending(false);
    }
  }

  // 3. Handle requesting a new link
  async function handleResend(e: React.FormEvent) {
    e.preventDefault();
    if (!resendEmail || resendPending || resendDone) return;
    setResendPending(true);
    setResendMessage("");

    try {
      const response = await fetch(`${API_BASE}/users/resend-activation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: resendEmail }),
      });

      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.detail || "Failed to send activation link.");
      }

      setResendMessage(body.message || "If an account with this email needs activation, we've sent a new link.");
      setResendDone(true);
    } catch (err) {
      setResendMessage(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setResendPending(false);
    }
  }

  if (!key) return <p style={{ textAlign: "center", marginTop: "40px" }}>The activation link is missing its key.</p>;

  if (isValidating) {
    return <p style={{ textAlign: "center", marginTop: "40px" }}>Checking activation link...</p>;
  }

  // Handle Already Active state (e.g. clicking an old link twice)
  if (isAlreadyActive) {
    return (
      <div style={{ maxWidth: 360, margin: "24px auto", textAlign: "center" }}>
        <h2>Account Already Active</h2>
        <p>This account has already been activated. You can log in directly.</p>
        <p style={{ marginTop: "20px" }}>
          <Link to="/login" style={{ fontWeight: "bold" }}>Go to Login</Link>
        </p>
      </div>
    );
  }

  // Handle Expired / Invalid state with inline resend form
  if (!tokenValid) {
    return (
      <div style={{ maxWidth: 360, margin: "24px auto", textAlign: "center" }}>
        <h2>Link Expired or Invalid</h2>
        <p>This activation link has expired or has already been used.</p>
        
        {resendDone ? (
          <>
            <p role="status">{resendMessage}</p>
            <p>Check your inbox and spam folder. Delivery may take a moment.</p>
            <Link to="/login">Back to login</Link>
          </>
        ) : (
        <form onSubmit={handleResend} style={{ marginTop: "20px", textAlign: "left" }}>
          <label style={{ display: "block", fontSize: "14px", marginBottom: "6px" }}>
            Enter your email to receive a new link:
          </label>
          <input
            type="email"
            required
            disabled={resendPending}
            placeholder="your@email.com"
            value={resendEmail}
            onChange={(e) => setResendEmail(e.target.value)}
            style={{ width: "100%", padding: "8px", marginBottom: "10px", boxSizing: "border-box" }}
          />
          <button disabled={resendPending} style={{ width: "100%", padding: "8px" }}>
            {resendPending ? "Sending..." : "Resend Activation Link"}
          </button>
          {resendMessage && (
            <p role="alert" style={{ marginTop: "10px", fontSize: "14px", color: "#333" }}>
              {resendMessage}
            </p>
          )}
        </form>
        )}
      </div>
    );
  }

  // Handle successful completion state
  if (done)
    return (
      <div style={{ textAlign: "center", marginTop: "40px" }}>
        <p>Your account is active! Redirecting to login...</p>
        <p>
          Or click here if you are not redirected: <Link to="/login">Log in</Link>
        </p>
      </div>
    );

  // Show password creation form
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
      {error && <p role="alert" style={{ color: "red" }}>{error}</p>}
      <button disabled={pending}>
        {pending ? "Activating…" : "Activate account"}
      </button>
    </form>
  );
}
