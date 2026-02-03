import { API_BASE, getToken } from "./auth";

export interface InAppNotification {
  id: string;
  event_id: string;
  home_id: string;
  subject: string | null;
  message: string;
  read_at: string | null;
  created_at: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function listInbox(params: {
  homeId?: string;
  unreadOnly?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<InAppNotification[]> {
  const token = getToken();
  const search = new URLSearchParams();
  if (params.homeId) {
    search.set("home_id", params.homeId);
  }
  if (typeof params.unreadOnly === "boolean") {
    search.set("unread_only", params.unreadOnly ? "true" : "false");
  }
  if (typeof params.limit === "number") {
    search.set("limit", String(params.limit));
  }
  if (typeof params.offset === "number") {
    search.set("offset", String(params.offset));
  }

  const res = await fetch(
    `${API_BASE}/notifications/inbox${search.toString() ? `?${search}` : ""}`,
    {
      method: "GET",
      headers: {
        ...(token ? { Authorization: `bearer ${token}` } : {}),
      },
    }
  );
  return handleResponse<InAppNotification[]>(res);
}

export async function unreadCount(homeId?: string): Promise<number> {
  const token = getToken();
  const search = new URLSearchParams();
  if (homeId) {
    search.set("home_id", homeId);
  }
  const res = await fetch(
    `${API_BASE}/notifications/unread-count${search.toString() ? `?${search}` : ""}`,
    {
      method: "GET",
      headers: {
        ...(token ? { Authorization: `bearer ${token}` } : {}),
      },
    }
  );
  const data = await handleResponse<{ unread: number }>(res);
  return data.unread;
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/notifications/${notificationId}/read`, {
    method: "PATCH",
    headers: {
      ...(token ? { Authorization: `bearer ${token}` } : {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
}
