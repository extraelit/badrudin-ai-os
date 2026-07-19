/*
 * Клиент backend-API модуля «Персонал объектов».
 *
 * Все вызовы идут через backend — единственную точку доступа к данным
 * (ARCHITECTURE.md раздел 5.2). Реальные секреты в коде не хранятся: базовый URL
 * берётся из переменной окружения, токен (если есть) — из хранилища сессии.
 *
 * В демонстрационном режиме (backend недоступен или нет токена) вызовы мягко
 * завершаются ошибкой, и интерфейс использует mock-данные без изменения дизайна.
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
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()) as T;
}

/* ------------------------------ Типы ответов ---------------------------- */

export interface ApiSiteSummary {
  site_id: string;
  site_name: string;
  workers: number;
  on_site: number;
  hours_day: number;
  overtime: number;
  idle: number;
  without_clearance: number;
  unfilled_journals: number;
}

export interface ApiDirectorSummary {
  sites: ApiSiteSummary[];
  total_workers: number;
  total_on_site: number;
  total_without_clearance: number;
  total_unfilled_journals: number;
}

export interface ApiWorker {
  id: string;
  employee_id: string;
  full_name: string | null;
  brigade: string | null;
  profession: string | null;
  is_responsible: boolean;
  status: string;
  clearance_status: string | null;
}

export interface ApiPayrollLine {
  id: string;
  employee_id: string;
  scheme: string;
  rate: string;
  quantity: string;
  unit: string | null;
  accrued: string;
  advance: string;
  deduction: string;
  to_pay: string;
  status: string;
}

export interface ApiPayrollDraft {
  id: string;
  site_id: string;
  period_start: string;
  period_end: string;
  status: string;
  total_accrued: string;
  total_advance: string;
  total_deduction: string;
  total_to_pay: string;
  currency: string;
  risk_level: string;
  approval_id: string | null;
  lines: ApiPayrollLine[];
}

/* ------------------------------- Методы --------------------------------- */

export const personnelApi = {
  getDirectorSummary: () =>
    api<ApiDirectorSummary>("/personnel/director/summary"),
  listWorkers: (siteId: string) =>
    api<ApiWorker[]>(`/personnel/sites/${siteId}/workers`),
  listTimesheet: (siteId: string) =>
    api<unknown[]>(`/personnel/sites/${siteId}/timesheet`),
  listSafety: (siteId: string) =>
    api<unknown[]>(`/personnel/sites/${siteId}/safety`),
  listJournals: (siteId: string) =>
    api<unknown[]>(`/personnel/sites/${siteId}/journals`),
  listPayroll: (siteId: string) =>
    api<ApiPayrollDraft[]>(`/personnel/sites/${siteId}/payroll`),
  requestPayout: (draftId: string) =>
    api<ApiPayrollDraft>(`/personnel/payroll/${draftId}/request-payout`, {
      method: "POST",
    }),
  decidePayout: (draftId: string, decision: "approved" | "rejected", mfaCode?: string) =>
    api<ApiPayrollDraft>(`/personnel/payroll/${draftId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, mfa_code: mfaCode }),
    }),
};
