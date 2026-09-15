import React, { useCallback, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Register from "./components/Register";
import ActivateAccount from "./components/ActivateAccount";
import PasswordReset from "./components/PasswordReset";
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
          {authed && (
            <NotificationBell
              onSelectItem={(notification) => {
                console.log("Global Notification Clicked:", notification);
                if (notification.home_id) {
                  // Extract potential item name from subject (e.g. "Expired: oilve oil" -> "oilve oil")
                  const itemName = notification.subject?.includes(":")
                    ? notification.subject.split(":")[1].trim()
                    : "";

                  // Navigate with both home and item query params
                  navigate(
                    `/?home=${notification.home_id}&highlight=${encodeURIComponent(itemName)}`,
                  );
                }
              }}
            />
          )}
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
            <Link to="/register" style={navActionStyle}>
              Register
            </Link>
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
            path="/register"
            element={authed ? <Navigate to="/" replace /> : <Register />}
          />
          <Route path="/forgot-password" element={<PasswordReset key="request" />} />
          <Route path="/reset-password/:token" element={<PasswordReset key="confirm" confirm />} />
          <Route path="/activate/:key" element={<ActivateAccount />} />
          <Route
            path="/login"
            element={
              authed ? <Navigate to="/" replace /> : <Login onLogin={onLogin} />
            }
          />
          <Route
            path="/"
            element={
              authed ? (
                <InventoryHome onLogout={onLogout} />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route
            path="/subscriptions"
            element={
              authed ? (
                <NotificationSubscriptions onLogout={onLogout} />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route
            path="*"
            element={<Navigate to={authed ? "/" : "/login"} replace />}
          />
        </Routes>
      </main>
    </div>
  );
}
