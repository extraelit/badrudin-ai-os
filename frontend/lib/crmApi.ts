/*
 * Клиент backend-API модуля «Ядро CRM».
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

export interface ApiFunnelRow {
  stage_id: string;
  name: string;
  sort_order: number;
  deals_count: number;
  amount: string;
}

export interface ApiManagerRow {
  employee_id: string | null;
  deals_total: number;
  won_count: number;
  won_amount: string;
  target_amount: string;
  plan_fact_percent: string;
}

export interface ApiCrmAnalytics {
  deals_total: number;
  open_count: number;
  won_count: number;
  lost_count: number;
  open_amount: string;
  won_amount: string;
  lost_amount: string;
  conversion_percent: string;
  funnel: ApiFunnelRow[];
  loss_reasons: { reason_id: string | null; count: number; amount: string }[];
  managers: ApiManagerRow[];
}

export const crmApi = {
  getAnalytics: (year?: number) =>
    api<ApiCrmAnalytics>(`/crm/analytics/summary${year ? `?period_year=${year}` : ""}`),
  listStages: () => api<unknown[]>("/crm/pipeline/stages"),
  listLeads: () => api<unknown[]>("/crm/leads"),
  convertLead: (leadId: string, body: Record<string, unknown>) =>
    api<unknown>(`/crm/leads/${leadId}/convert`, { method: "POST", body: JSON.stringify(body) }),
  listDeals: () => api<unknown[]>("/crm/deals"),
  requestWin: (dealId: string) =>
    api<unknown>(`/crm/deals/${dealId}/request-win`, { method: "POST" }),
  winDecision: (dealId: string, decision: "approved" | "rejected", mfaCode?: string) =>
    api<unknown>(`/crm/deals/${dealId}/win-decision`, {
      method: "POST",
      body: JSON.stringify({ decision, mfa_code: mfaCode }),
    }),
  listCounterparties: () => api<unknown[]>("/crm/counterparties"),
  listContacts: (counterpartyId: string) =>
    api<unknown[]>(`/crm/counterparties/${counterpartyId}/contacts`),
  listCommunications: () => api<unknown[]>("/crm/communications"),
  communicationCreateTask: (commId: string, title: string) =>
    api<unknown>(`/crm/communications/${commId}/create-task`, {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  listContracts: () => api<unknown[]>("/crm/contracts"),
  decideContract: (contractId: string, decision: "approved" | "rejected", mfaCode?: string) =>
    api<unknown>(`/crm/contracts/${contractId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, mfa_code: mfaCode }),
    }),
};
