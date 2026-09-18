import { API_BASE, getToken } from "./auth";

export interface HouseholdCategory { id: string; name: string; home_id: string; }

export async function listInventoryCategories(homeId: string): Promise<HouseholdCategory[]> {
  const token = getToken();
  const response = await fetch(`${API_BASE}/inventory/${homeId}/categories`, {
    headers: { ...(token ? { Authorization: `bearer ${token}` } : {}) },
  });
  return handleResponse<HouseholdCategory[]>(response);
}

export interface InventoryCreateRequest {
  product_id: string;
  household_category_id: string;
  quantity: number;
  unit: string;
  expiry_date?: string; // ISO date yyyy-mm-dd
  notes?: string;
}

export interface InventoryItem {
  product_id: string;
  id: string;
  name: string;
  household_category_id: string;
  quantity: number;
  unit: string;
  expiry_date?: string;
  notes?: string;
  home_id: string;
}

export interface InventoryUpdateRequest {
  product_id?: string;
  household_category_id?: string;
  quantity?: number;
  unit?: string;
  expiry_date?: string | null;
  notes?: string | null;
}

export interface PaginatedInventoryResponse {
  count: number;
  total_pages: number;
  next: string | null;
  previous: string | null;
  results: InventoryItem[];
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function listInventoryItems(
  homeId: string,
): Promise<PaginatedInventoryResponse> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/inventory/${homeId}`, {
    method: "GET",
    headers: {
      ...(token ? { Authorization: `bearer ${token}` } : {}),
    },
  });
  return handleResponse<PaginatedInventoryResponse>(res);
}

export async function createInventoryItem(
  homeId: string,
  payload: InventoryCreateRequest,
): Promise<InventoryItem[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/inventory/${homeId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `bearer ${token}` } : {}),
    },
    body: JSON.stringify([payload]),
  });
  return handleResponse<InventoryItem[]>(res);
}

export async function updateInventoryItem(
  homeId: string,
  itemId: string,
  payload: InventoryUpdateRequest,
): Promise<InventoryItem> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/inventory/${homeId}/${itemId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  return handleResponse<InventoryItem>(res);
}

export async function deleteInventoryItem(
  homeId: string,
  itemId: string,
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/inventory/${homeId}/${itemId}`, {
    method: "DELETE",
    headers: {
      ...(token ? { Authorization: `bearer ${token}` } : {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
}

export interface Product { id: string; name: string; }
export async function searchProducts(name: string): Promise<Product[]> {
  const token = getToken();
  return handleResponse<Product[]>(await fetch(`${API_BASE}/products?q=${encodeURIComponent(name)}`, {
    headers: { ...(token ? { Authorization: `bearer ${token}` } : {}) },
  }));
}
export async function createProduct(name: string): Promise<Product> {
  const token = getToken();
  return handleResponse<Product>(await fetch(`${API_BASE}/products`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `bearer ${token}` } : {}) },
    body: JSON.stringify({ name }),
  }));
}
