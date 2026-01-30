import { API_BASE, getToken } from "./auth";

export interface InventoryCreateRequest {
  name: string;
  quantity?: number;
  unit?: string;
  expiry_date?: string; // ISO date yyyy-mm-dd
  notes?: string;
  category?: string;
  home_id?: string;
}

export interface InventoryCreateResponse {
  id: string;
  name: string;
  quantity?: number;
  expiry_date?: string;
  created_at?: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function createInventoryItem(payload: InventoryCreateRequest): Promise<InventoryCreateResponse> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/inventory/items`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  return handleResponse<InventoryCreateResponse>(res);
}
