/*
 * Клиент backend-API модуля «Снабжение и закупки».
 * Вызовы идут через backend; базовый URL — из переменной окружения, токен — из
 * хранилища сессии. Секреты в коде не хранятся. В демо-режиме (нет backend/
 * токена) вызовы мягко завершаются ошибкой, интерфейс использует mock-данные.
 */

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) || "";

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("badrudin_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) throw new Error("API base URL не задан (демо-режим)");
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers || {}) },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()) as T;
}

export interface ApiProcurementSummary {
  requests_open: number;
  orders_pending: number;
  orders_active: number;
  writeoffs_pending: number;
  warehouses: number;
  stock_positions: number;
}

export const procurementApi = {
  getSummary: () => api<ApiProcurementSummary>("/procurement/summary"),
  listWarehouses: () => api<unknown[]>("/procurement/warehouses"),
  listBalances: (warehouseId: string) =>
    api<unknown[]>(`/procurement/warehouses/${warehouseId}/balances`),
  listRequests: (projectId: string) =>
    api<unknown[]>(`/procurement/projects/${projectId}/requests`),
  decideOrder: (orderId: string, decision: "approved" | "rejected", mfaCode?: string) =>
    api<unknown>(`/procurement/orders/${orderId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, mfa_code: mfaCode }),
    }),
  postReceipt: (receiptId: string) =>
    api<unknown>(`/procurement/receipts/${receiptId}/post`, { method: "POST" }),
  postIssue: (issueId: string) =>
    api<unknown>(`/procurement/issues/${issueId}/post`, { method: "POST" }),
};
