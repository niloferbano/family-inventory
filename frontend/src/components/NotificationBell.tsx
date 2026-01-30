import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listNotifications, NotificationEvent } from "../api/notifications";

const POLL_MS = 15000;
const LAST_SEEN_KEY = "notifications_last_seen_at";

const isUnauthorized = (err: unknown) => {
  const message = String(err ?? "");
  return message.includes("401") || message.toLowerCase().includes("unauthorized");
};

const toMs = (value: string | null | undefined) => {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
};

const formatTimestamp = (value: string | null | undefined) => {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

export default function NotificationBell({ onLogout }: { onLogout: () => void }) {
  const [notifications, setNotifications] = useState<NotificationEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [lastSeenAt, setLastSeenAt] = useState<string | null>(
    () => localStorage.getItem(LAST_SEEN_KEY)
  );
  const containerRef = useRef<HTMLDivElement | null>(null);

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listNotifications({ limit: 20 });
      const sorted = [...data].sort(
        (a, b) => toMs(b.created_at) - toMs(a.created_at)
      );
      setNotifications(sorted);
      setError(null);
    } catch (err) {
      if (isUnauthorized(err)) {
        onLogout();
        return;
      }
      setError((err as Error)?.message ?? "Failed to load notifications.");
    } finally {
      setLoading(false);
    }
  }, [onLogout]);

  useEffect(() => {
    void loadNotifications();
    const id = window.setInterval(() => {
      void loadNotifications();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [loadNotifications]);

  const unreadCount = useMemo(() => {
    const lastSeenMs = toMs(lastSeenAt);
    return notifications.filter((notice) => toMs(notice.created_at) > lastSeenMs)
      .length;
  }, [lastSeenAt, notifications]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const latest = notifications[0]?.created_at;
    if (!latest) {
      return;
    }
    setLastSeenAt(latest);
    localStorage.setItem(LAST_SEEN_KEY, latest);
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
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", handleClick);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handleClick);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

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
        {unreadCount > 0 && (
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
            {unreadCount}
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
          <div style={{ fontWeight: 600, marginBottom: 8 }}>
            Notifications
          </div>
          {loading && <div style={{ color: "#666" }}>Loading...</div>}
          {error && <div style={{ color: "crimson" }}>{error}</div>}
          {!loading && notifications.length === 0 && (
            <div style={{ color: "#666" }}>No notifications yet.</div>
          )}
          <div style={{ display: "grid", gap: 8 }}>
            {notifications.map((notice) => {
              const isUnread =
                toMs(notice.created_at) > toMs(lastSeenAt);
              return (
                <div
                  key={notice.event_id}
                  style={{
                    border: "1px solid #f0f0f0",
                    borderRadius: 10,
                    padding: 10,
                    background: isUnread ? "#f7f9ff" : "#fafafa",
                  }}
                >
                  <div style={{ fontSize: 11, color: "#666" }}>
                    {formatTimestamp(notice.created_at)}
                  </div>
                  <div style={{ fontWeight: 600, marginTop: 4 }}>
                    {notice.subject ?? notice.event_type}
                  </div>
                  <div style={{ fontSize: 13, color: "#444", marginTop: 4 }}>
                    {notice.message}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
