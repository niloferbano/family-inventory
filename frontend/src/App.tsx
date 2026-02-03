import React, { useCallback, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Login from "./components/Login";
import InventoryHome from "./components/InventoryHome";
import { getToken, clearToken } from "./api/auth";
import NotificationBell from "./components/NotificationBell";

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
          {!authed && (
            <Link to="/login" style={{ textDecoration: "none" }}>
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
          <Route path="*" element={<Navigate to={authed ? "/" : "/login"} replace />} />
        </Routes>
      </main>
    </div>
  );
}
