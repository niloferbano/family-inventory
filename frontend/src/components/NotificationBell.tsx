import React, { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, getToken } from "../api/auth";
import {
  InAppNotification,
  listInbox,
  markNotificationRead,
  unreadCount,
} from "../api/notifications";

const MAX_ITEMS = 20;
const RECONNECT_DELAY_MS = 5000;

const buildWsUrl = (token: string) => {
  if (API_BASE.startsWith("http")) {
    const url = new URL(API_BASE);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = `${url.pathname.replace(/\/$/, "")}/notifications/ws`;
    url.searchParams.set("token", token);
    return url.toString();
  }

  const basePath = API_BASE.startsWith("/") ? API_BASE : `/${API_BASE}`;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}${basePath.replace(
    /\/$/,
    ""
  )}/notifications/ws?token=${encodeURIComponent(token)}`;
};

const formatTimestamp = (value: string | null) => {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

export default function NotificationBell() {
  const [notifications, setNotifications] = useState<InAppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const loadInbox = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listInbox({ limit: MAX_ITEMS });
      setNotifications(data);
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to load inbox.");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshUnread = useCallback(async () => {
    try {
      const count = await unreadCount();
      setUnread(count);
    } catch {
      // ignore unread count failure
    }
  }, []);

  useEffect(() => {
    void loadInbox();
    void refreshUnread();
  }, [loadInbox, refreshUnread]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const unreadItems = notifications.filter((item) => !item.read_at);
    if (unreadItems.length === 0) {
      return;
    }
    const markAll = async () => {
      await Promise.all(
        unreadItems.map((item) =>
          markNotificationRead(item.id).catch(() => null)
        )
      );
      const now = new Date().toISOString();
      setNotifications((prev) =>
        prev.map((item) =>
          unreadItems.some((unreadItem) => unreadItem.id === item.id)
            ? { ...item, read_at: item.read_at ?? now }
            : item
        )
      );
      setUnread(0);
    };
    void markAll();
  }, [open, notifications]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handleClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", handleClick);
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("mousedown", handleClick);
      window.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let closed = false;

    const connect = () => {
      if (closed) {
        return;
      }
      const wsUrl = buildWsUrl(token);
      socket = new WebSocket(wsUrl);

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload?.type !== "notification.in_app.created") {
            return;
          }
          const incoming = payload.data as InAppNotification | undefined;
          if (!incoming?.id) {
            return;
          }
          setNotifications((prev) => {
            const next = [
              incoming,
              ...prev.filter((item) => item.id !== incoming.id),
            ];
            return next.slice(0, MAX_ITEMS);
          });
          void refreshUnread();
        } catch {
          // ignore malformed payloads
        }
      };

      socket.onclose = () => {
        if (closed) {
          return;
        }
        reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
      };

      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      if (socket && socket.readyState < WebSocket.CLOSING) {
        socket.close();
      }
    };
  }, [refreshUnread]);

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label="Notifications"
        title="Notifications"
        style={{
          position: "relative",
          border: "1px solid #e5e5e5",
          borderRadius: 999,
          padding: "6px 10px",
          background: "#fff",
          cursor: "pointer",
        }}
      >
        <svg
          viewBox="0 0 24 24"
          width="18"
          height="18"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 8a6 6 0 10-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
          <path d="M13.73 21a2 2 0 01-3.46 0" />
        </svg>
        {unread > 0 && (
          <span
            style={{
              position: "absolute",
              top: -4,
              right: -4,
              minWidth: 16,
              height: 16,
              padding: "0 4px",
              borderRadius: 999,
              background: "#ff4d4f",
              color: "#fff",
              fontSize: 10,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 0 2px #fff",
            }}
          >
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 10px)",
            right: 0,
            width: 320,
            maxHeight: 360,
            overflowY: "auto",
            background: "#fff",
            border: "1px solid #e8e8e8",
            borderRadius: 12,
            padding: 12,
            boxShadow: "0 12px 24px rgba(0, 0, 0, 0.12)",
            zIndex: 20,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Notifications</div>
          {loading && <div style={{ color: "#666" }}>Loading...</div>}
          {error && <div style={{ color: "crimson" }}>{error}</div>}
          {!loading && notifications.length === 0 && (
            <div style={{ color: "#666" }}>No notifications yet.</div>
          )}
          <div style={{ display: "grid", gap: 8 }}>
            {notifications.map((item) => (
              <div
                key={item.id}
                style={{
                  border: "1px solid #f0f0f0",
                  borderRadius: 10,
                  padding: 10,
                  background: item.read_at ? "#fafafa" : "#f7f9ff",
                }}
              >
                <div style={{ fontSize: 11, color: "#666" }}>
                  {formatTimestamp(item.created_at)}
                </div>
                <div style={{ fontWeight: 600, marginTop: 4 }}>
                  {item.subject ?? "Notification"}
                </div>
                <div style={{ fontSize: 13, color: "#444", marginTop: 4 }}>
                  {item.message}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
