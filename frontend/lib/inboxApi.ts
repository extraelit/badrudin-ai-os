/*
 * Клиент backend-API «Единый входящий поток» (рабочий контур). Приём обращений,
 * классификация, назначение, конверсия в задачу, отклонение. Вызовы идут через
 * backend с JWT из хранилища сессии; базовый URL — из NEXT_PUBLIC_API_BASE_URL.
 * Без backend экраны показывают пустое состояние, а не mock-данные. Секреты в
 * коде не хранятся.
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

export interface InboxItem {
  id: string; source_type: string; channel: string; subject: string | null;
  body_text: string | null; status: string; category: string | null; priority: string;
  project_id: string | null; counterparty_id: string | null;
  assigned_to_employee_id: string | null; converted_entity_type: string | null;
  converted_entity_id: string | null; received_at: string | null;
}
export interface InboxSummary {
  new: number; classified: number; in_progress: number; converted: number;
  dismissed: number; unresolved: number;
}

export const inboxApi = {
  summary: () => api<InboxSummary>("/inbox/summary"),
  list: (status?: string) => api<InboxItem[]>(`/inbox${status ? `?status=${status}` : ""}`),
  capture: (body: { subject?: string; body_text?: string; channel?: string }) =>
    api<InboxItem>("/inbox", { method: "POST", body: JSON.stringify(body) }),
  classify: (id: string, body: { category: string; priority?: string; project_id?: string; assigned_to_employee_id?: string }) =>
    api<InboxItem>(`/inbox/${id}/classify`, { method: "POST", body: JSON.stringify(body) }),
  convertToTask: (id: string, body: { title?: string; description?: string }) =>
    api<{ id: string; title: string; status: string }>(`/inbox/${id}/convert-to-task`, { method: "POST", body: JSON.stringify(body) }),
  markConverted: (id: string, entityType: string, note?: string) =>
    api<InboxItem>(`/inbox/${id}/mark-converted`, { method: "POST", body: JSON.stringify({ entity_type: entityType, note }) }),
  dismiss: (id: string, reason: string) =>
    api<InboxItem>(`/inbox/${id}/dismiss`, { method: "POST", body: JSON.stringify({ reason }) }),
};
