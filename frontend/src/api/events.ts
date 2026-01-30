import { API_BASE, getToken } from "./auth";

export interface EventCreateRequest {
  subject: string;
  message: string;
  recipients?: Array<{ channel: string; recipient: string }>;
  source?: string;
}

export interface EventCreateResponse {
  event_id: string;
  created_at?: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function createEvent(payload: EventCreateRequest): Promise<EventCreateResponse> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/notifications/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  return handleResponse<EventCreateResponse>(res);
}
