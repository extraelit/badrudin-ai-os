/*
 * Клиент backend-API модуля «Сметы и ценообразование».
 * Вызовы идут через backend; базовый URL — из переменной окружения, токен —
 * из хранилища сессии. Секреты в коде не хранятся. В демо-режиме (нет backend/
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

export interface ApiEstimateSummary {
  project_id: string;
  estimates_total: number;
  approved_total: number;
  grand_total_approved: string;
  offers_pending: number;
  estimates: { estimate_id: string; name: string; version: number; status: string; grand_total: string }[];
}

export const estimatesApi = {
  getSummary: (projectId: string) =>
    api<ApiEstimateSummary>(`/estimates/projects/${projectId}/summary`),
  listEstimates: (projectId: string) =>
    api<unknown[]>(`/estimates/projects/${projectId}/estimates`),
  getEstimate: (estimateId: string) => api<unknown>(`/estimates/${estimateId}`),
  approve: (estimateId: string) =>
    api<unknown>(`/estimates/${estimateId}/approve`, { method: "POST" }),
  planFact: (estimateId: string) => api<unknown>(`/estimates/${estimateId}/plan-fact`),
  createOffer: (estimateId: string, markupPercent: number) =>
    api<unknown>(`/estimates/${estimateId}/offers`, {
      method: "POST",
      body: JSON.stringify({ markup_percent: markupPercent }),
    }),
  decideOffer: (offerId: string, decision: "approved" | "rejected", mfaCode?: string) =>
    api<unknown>(`/estimates/offers/${offerId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, mfa_code: mfaCode }),
    }),
  listRateItems: () => api<unknown[]>(`/estimates/rate-items`),
};
