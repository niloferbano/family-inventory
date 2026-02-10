import { API_BASE, getToken } from "./auth";

export type UserType = "owner" | "residence" | "guest";

export interface HomeMember {
  user_id: string;
  username: string;
  email: string;
  user_type: UserType;
}

export interface HomeSummary {
  home_id: string;
  name: string;
  members?: HomeMember[];
}

export interface HomeCreateRequest {
  name: string;
}

export interface HomeRead {
  id: string;
  name: string;
  user_type?: UserType;
  created_at: string;
  updated_at: string;
}

export interface HomeMemberAddResponse {
  username: string;
  home_name: string;
  user_type: UserType;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    // Attempt to get error details, fallback to status text
    const errorData = await res.json().catch(() => null);
    const message = errorData?.message || await res.text() || res.statusText;
    throw new Error(`HTTP ${res.status}: ${message}`);
  }
  
  // Handle empty bodies for 204 No Content
  if (res.status === 204) return {} as T;

  return res.json();
}

export async function listHomes(): Promise<HomeSummary[]> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Accept": "application/json",
  };

  if (token) {
    headers["Authorization"] = `bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}/homes/`, {
    method: "GET",
    headers,
  });

  return handleResponse<HomeSummary[]>(res);
}

export async function createHome(payload: HomeCreateRequest): Promise<HomeRead> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (token) {
    headers["Authorization"] = `bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}/homes/`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  return handleResponse<HomeRead>(res);
}

export async function addHomeMember(
  homeId: string,
  payload: { userEmail: string; userType: UserType }
): Promise<HomeMemberAddResponse> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (token) {
    headers["Authorization"] = `bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}/homeuser/${homeId}/users`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      user_email: payload.userEmail,
      user_type: payload.userType,
    }),
  });

  return handleResponse<HomeMemberAddResponse>(res);
}
