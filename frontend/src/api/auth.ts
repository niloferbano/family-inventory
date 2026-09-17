export const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

export interface LoginResponse {
  access_token: string;
  token_type?: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/users/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse<LoginResponse>(res);
}

export function saveToken(token: string) {
  localStorage.setItem("auth_token", token);
  localStorage.removeItem("token");
  localStorage.removeItem("access_token");
}

export function getToken(): string | null {
  const raw =
    localStorage.getItem("auth_token") ??
    localStorage.getItem("token") ??
    localStorage.getItem("access_token");

  if (!raw) {
    return null;
  }

  const trimmed = raw.trim();
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1);
  }

  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed === "string") {
      return parsed;
    }
    if (parsed && typeof parsed.access_token === "string") {
      return parsed.access_token;
    }
  } catch {
    // Not JSON, fall through to return raw string.
  }

  return raw;
}

export function clearToken() {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("token");
  localStorage.removeItem("access_token");
}

export async function register(
  username: string,
  email: string,
): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/users/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, email }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((issue: { msg?: string }) => issue.msg || "Invalid field")
              .join("; ")
          : "Registration failed. Please try again later.";
    throw new Error(message);
  }
  return body;
}

export async function resendActivation(email: string): Promise<void> {
  const response = await fetch(`${API_BASE}/users/resend-activation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) {
    throw new Error("Unable to request an activation link. Please try again later.");
  }
}

async function passwordResetRequest(path: string, payload: object): Promise<void> {
  const response = await fetch(`${API_BASE}/users/password-reset/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Unable to reset your password. Check your details and try again.",
    );
  }
}

export function requestPasswordReset(email: string): Promise<void> {
  return passwordResetRequest("request", { email });
}

export function resetPassword(token: string, password: string, confirmation: string): Promise<void> {
  return passwordResetRequest("confirm", { token, password, confirm_password: confirmation });
}
