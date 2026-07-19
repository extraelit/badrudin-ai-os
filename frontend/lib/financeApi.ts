/*
 * Клиент backend-API модуля «Финансы и бюджеты».
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

export interface ApiSummaryComponent {
  label: string;
  amount: string;
  source: string;
}

export interface ApiFinancialSummary {
  project_id: string;
  currency: string;
  approved_budget: string;
  planned_budget: string;
  committed: string;
  actual: string;
  remaining: string;
  forecast: string;
  forecast_deviation: string;
  has_approved_budget: boolean;
  committed_breakdown: ApiSummaryComponent[];
  actual_breakdown: ApiSummaryComponent[];
}

export const financeApi = {
  getSummary: (projectId: string) =>
    api<ApiFinancialSummary>(`/finance/projects/${projectId}/financial-summary`),
  listBudgets: (projectId: string) =>
    api<unknown[]>(`/finance/projects/${projectId}/budgets`),
  getBudget: (budgetId: string) => api<unknown>(`/finance/budgets/${budgetId}`),
  budgetFromEstimate: (projectId: string, estimateId: string) =>
    api<unknown>(`/finance/projects/${projectId}/budgets/from-estimate`, {
      method: "POST",
      body: JSON.stringify({ estimate_id: estimateId }),
    }),
  decideBudget: (budgetId: string, decision: "approved" | "rejected", mfaCode?: string) =>
    api<unknown>(`/finance/budgets/${budgetId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, mfa_code: mfaCode }),
    }),
  listCommitments: (projectId: string) =>
    api<unknown[]>(`/finance/projects/${projectId}/commitments`),
  exportSummary: (projectId: string, format: "csv" | "json") =>
    `${API_BASE}/finance/projects/${projectId}/financial-summary/export?format=${format}`,
};

export const financePaymentsApi = {
  listInvoices: (projectId: string) => api<unknown[]>(`/finance/projects/${projectId}/invoices`),
  registerInvoice: (invoiceId: string) =>
    api<unknown>(`/finance/invoices/${invoiceId}/register`, { method: "POST" }),
  createPaymentRequest: (invoiceId: string, body: Record<string, unknown>) =>
    api<unknown>(`/finance/invoices/${invoiceId}/payment-requests`, { method: "POST", body: JSON.stringify(body) }),
  listPaymentRequests: (projectId: string) => api<unknown[]>(`/finance/projects/${projectId}/payment-requests`),
  decidePaymentRequest: (prId: string, decision: "approved" | "rejected", mfaCode?: string) =>
    api<unknown>(`/finance/payment-requests/${prId}/decision`, { method: "POST", body: JSON.stringify({ decision, mfa_code: mfaCode }) }),
  recordPayment: (prId: string, body: Record<string, unknown>) =>
    api<unknown>(`/finance/payment-requests/${prId}/payments`, { method: "POST", body: JSON.stringify(body) }),
  listPayments: (projectId: string) => api<unknown[]>(`/finance/projects/${projectId}/payments`),
  getPayablesSummary: (projectId: string) => api<unknown>(`/finance/projects/${projectId}/payables-summary`),
};
