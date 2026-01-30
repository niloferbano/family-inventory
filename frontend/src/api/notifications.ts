import { API_BASE, getToken } from "./auth";

export interface NotificationEvent {
  event_id: string;
  source: string;
  event_type: string;
  subject?: string | null;
  message: string;
  created_at: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function listNotifications(params: {
  since?: string;
  limit?: number;
} = {}): Promise<NotificationEvent[]> {
  const token = getToken();
  const search = new URLSearchParams();
  if (params.since) {
    search.set("since", params.since);
  }
  if (params.limit) {
    search.set("limit", String(params.limit));
  }
  const url = `${API_BASE}/notifications/events${search.toString() ? `?${search}` : ""}`;
  const res = await fetch(url, {
    method: "GET",
    headers: {
      ...(token ? { Authorization: `bearer ${token}` } : {}),
    },
  });
  return handleResponse<NotificationEvent[]>(res);
}
