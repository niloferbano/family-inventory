import React, { useCallback, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Login from "./components/Login";
import InventoryHome from "./components/InventoryHome";
import { getToken, clearToken } from "./api/auth";
import NotificationBell from "./components/NotificationBell";
import NotificationSubscriptions from "./components/NotificationSubscriptions";

const navActionStyle: React.CSSProperties = {
  textDecoration: "none",
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid #e0e0e0",
  background: "#fff",
  color: "#1c1b1f",
  fontSize: 14,
  lineHeight: "20px",
};

export default function App() {
  const navigate = useNavigate();
  const [authed, setAuthed] = useState<boolean>(() => Boolean(getToken()));

  const onLogin = useCallback(() => {
    setAuthed(true);
    navigate("/", { replace: true });
  }, [navigate]);
  const onLogout = useCallback(() => {
    clearToken();
    setAuthed(false);
    navigate("/login", { replace: true });
  }, [navigate]);

  return (
    <div>
      <header
        style={{
          padding: 12,
          borderBottom: "1px solid #eee",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <h2 style={{ margin: 0 }}>Family Inventory</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {authed && <NotificationBell />}
          {authed && (
            <Link to="/subscriptions" style={navActionStyle}>
              Subscriptions
            </Link>
          )}
          {authed && (
            <button type="button" onClick={onLogout} style={navActionStyle}>
              Logout
            </button>
          )}
          {!authed && (
            <Link to="/login" style={navActionStyle}>
              Log in
            </Link>
          )}
        </div>
      </header>

      <main>
        <Routes>
          <Route
            path="/login"
            element={authed ? <Navigate to="/" replace /> : <Login onLogin={onLogin} />}
          />
          <Route
            path="/"
            element={authed ? <InventoryHome onLogout={onLogout} /> : <Navigate to="/login" replace />}
          />
          <Route
            path="/subscriptions"
            element={
              authed ? <NotificationSubscriptions onLogout={onLogout} /> : <Navigate to="/login" replace />
            }
          />
          <Route path="*" element={<Navigate to={authed ? "/" : "/login"} replace />} />
        </Routes>
      </main>
    </div>
  );
}
