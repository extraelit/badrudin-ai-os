/*
 * Клиент backend-API «Реестр рисков» (рабочий контур). Идентификация, оценка,
 * план снижения, принятие/закрытие рисков. Вызовы идут через backend с JWT из
 * хранилища сессии; базовый URL — из NEXT_PUBLIC_API_BASE_URL. Без backend экраны
 * показывают пустое состояние, а не mock-данные. Секреты в коде не хранятся.
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

export interface Risk {
  id: string; number: string | null; title: string; description: string | null;
  category: string; probability: string; impact: string; severity: string; status: string;
  project_id: string | null; owner_employee_id: string | null; mitigation_plan: string | null;
  due_at: string | null; source_type: string | null;
}
export interface RiskSummary {
  total: number; open: number; critical: number; high: number; accepted: number; realized: number;
}

export const riskApi = {
  summary: () => api<RiskSummary>("/risks/summary"),
  list: (severity?: string) => api<Risk[]>(`/risks${severity ? `?severity=${severity}` : ""}`),
  register: (body: { title: string; category?: string; probability?: string; impact?: string; project_id?: string; description?: string }) =>
    api<Risk>("/risks", { method: "POST", body: JSON.stringify(body) }),
  assess: (id: string, probability: string, impact: string) =>
    api<Risk>(`/risks/${id}/assess`, { method: "POST", body: JSON.stringify({ probability, impact }) }),
  mitigation: (id: string, mitigation_plan: string) =>
    api<Risk>(`/risks/${id}/mitigation`, { method: "POST", body: JSON.stringify({ mitigation_plan }) }),
  decide: (id: string, decision: "accepted" | "closed" | "realized", comment?: string) =>
    api<Risk>(`/risks/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, comment }) }),
};
