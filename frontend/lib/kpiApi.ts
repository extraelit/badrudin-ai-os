/*
 * Клиент backend-API «KPI и независимый аудит». KPI считаются только для чтения из
 * существующих данных; находки аудита — отдельные записи (проверяемые данные не
 * изменяются). Вызовы идут через backend с JWT из хранилища сессии; базовый URL — из
 * NEXT_PUBLIC_API_BASE_URL. Без backend экраны показывают пустое состояние, а не
 * mock-данные. Секреты в коде не хранятся.
 */
import { getToken } from "./authApi";

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) || "";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) throw new Error("Backend не настроен");
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()) as T;
}

export interface KpiSummary {
  tasks_total: number; tasks_completed: number; tasks_overdue: number; overdue_ratio: number;
  risks_open: number; risks_high: number; daily_reports_7d: number;
  findings_open: number; findings_high: number;
}
export interface Finding {
  id: string; category: string; severity: string; title: string; detail: string | null;
  entity_type: string | null; entity_id: string | null; status: string; detected_by: string;
  project_id: string | null; owner_user_id: string | null; resolution_note: string | null;
  created_at: string;
}

export const kpiApi = {
  summary: () => api<KpiSummary>("/kpi/summary"),
  listFindings: (status?: string) =>
    api<Finding[]>(`/kpi/findings${status ? `?status=${status}` : ""}`),
  createFinding: (body: { category: string; title: string; severity?: string; detail?: string }) =>
    api<Finding>("/kpi/findings", { method: "POST", body: JSON.stringify(body) }),
  resolve: (id: string, status: "acknowledged" | "resolved" | "false_positive", note?: string) =>
    api<Finding>(`/kpi/findings/${id}/resolve`, { method: "POST", body: JSON.stringify({ status, note }) }),
  scan: () => api<{ created: number }>("/kpi/scan", { method: "POST", body: "{}" }),
};
