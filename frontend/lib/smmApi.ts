/*
 * Клиент backend-API «SMM и внешние публикации» — внутренний контур. Контент-план
 * и публикации как черновики на утверждение (публикация не производится, секреты не
 * хранятся). Вызовы идут через backend с JWT из хранилища сессии; базовый URL — из
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

export interface PlanItem {
  id: string; title: string; theme: string | null; channel: string;
  planned_date: string | null; project_id: string | null; status: string; notes: string | null;
}
export interface Publication {
  id: string; channel: string; title: string | null; body_text: string | null;
  hashtags: string | null; status: string; rights_confirmed: boolean; pii_checked: boolean;
  legal_checked: boolean; scheduled_for: string | null; risk_level: string;
  project_id: string | null; connector_id: string | null; plan_item_id: string | null;
  approval_id: string | null; approved_at: string | null;
}
export interface SmmSummary {
  plan_total: number; plan_active: number; publications_draft: number;
  publications_pending: number; publications_approved: number;
}

export const smmApi = {
  summary: () => api<SmmSummary>("/smm/summary"),
  listPlan: () => api<PlanItem[]>("/smm/plan"),
  createPlan: (body: { title: string; theme?: string; channel?: string; project_id?: string }) =>
    api<PlanItem>("/smm/plan", { method: "POST", body: JSON.stringify(body) }),
  setPlanStatus: (id: string, status: string) =>
    api<PlanItem>(`/smm/plan/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
  listPublications: (status?: string) =>
    api<Publication[]>(`/smm/publications${status ? `?status=${status}` : ""}`),
  createPublication: (body: { channel: string; title?: string; body_text?: string; hashtags?: string; project_id?: string }) =>
    api<Publication>("/smm/publications", { method: "POST", body: JSON.stringify(body) }),
  setChecks: (id: string, checks: { rights_confirmed?: boolean; pii_checked?: boolean; legal_checked?: boolean }) =>
    api<Publication>(`/smm/publications/${id}/checks`, { method: "POST", body: JSON.stringify(checks) }),
  submit: (id: string) =>
    api<Publication>(`/smm/publications/${id}/submit`, { method: "POST", body: "{}" }),
  decide: (id: string, decision: "approved" | "rejected", comment?: string) =>
    api<Publication>(`/smm/publications/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, comment }) }),
  cancel: (id: string, reason: string) =>
    api<Publication>(`/smm/publications/${id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }),
};
