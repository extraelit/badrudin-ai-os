/*
 * Клиент аутентификации Badrudin AI OS.
 * Реальный вход через backend (/auth/login), хранение JWT в localStorage,
 * получение профиля (/auth/me) и выход (/auth/logout). Секреты в коде не хранятся;
 * базовый URL — из NEXT_PUBLIC_API_BASE_URL.
 */

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) || "";

const TOKEN_KEY = "badrudin_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

export function apiBaseConfigured(): boolean {
  return Boolean(API_BASE);
}

export interface CurrentUser {
  id: string;
  email: string;
  status: string;
  roles: string[];
  permissions: string[];
}

export class AuthError extends Error {
  code: number;
  constructor(code: number, message: string) {
    super(message);
    this.code = code;
  }
}

export async function login(email: string, password: string, mfaCode?: string): Promise<string> {
  if (!API_BASE) throw new AuthError(0, "Backend не настроен (NEXT_PUBLIC_API_BASE_URL)");
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, mfa_code: mfaCode }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new AuthError(res.status, (detail as { detail?: string }).detail || "Ошибка входа");
  }
  const data = (await res.json()) as { access_token: string };
  setToken(data.access_token);
  return data.access_token;
}

export async function me(): Promise<CurrentUser> {
  const token = getToken();
  if (!API_BASE || !token) throw new AuthError(401, "Не авторизован");
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new AuthError(res.status, "Сессия недействительна");
  return (await res.json()) as CurrentUser;
}

export async function logout(): Promise<void> {
  const token = getToken();
  if (API_BASE && token) {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => undefined);
  }
  clearToken();
}
