/*
 * Клиент backend-API «Исполнительная документация ПТО». Реестр исполнительной
 * документации с версионированием и инженерным согласованием; контроль обязательного
 * комплекта. Вызовы идут через backend с JWT из хранилища сессии; базовый URL — из
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

export interface ExecutiveDocument {
  id: string; project_id: string; doc_type: string; number: string | null; title: string;
  description: string | null; file_id: string | null; work_item_type: string | null;
  work_item_id: string | null; version_number: number; supersedes_id: string | null;
  status: string; approval_id: string | null; reviewed_by_user_id: string | null;
  review_comment: string | null; approved_at: string | null;
}
export interface Completeness {
  required: string[]; present: string[]; missing: string[]; complete: boolean;
}
export interface PtoSummary {
  documents_total: number; documents_draft: number; documents_under_review: number;
  documents_approved: number; documents_superseded: number;
}

export const ptoApi = {
  summary: () => api<PtoSummary>("/pto/summary"),
  listDocuments: (projectId?: string, status?: string) => {
    const q = new URLSearchParams();
    if (projectId) q.set("project_id", projectId);
    if (status) q.set("status", status);
    const s = q.toString();
    return api<ExecutiveDocument[]>(`/pto/documents${s ? `?${s}` : ""}`);
  },
  createDocument: (body: { project_id: string; doc_type: string; title: string; number?: string; file_id?: string; supersedes_id?: string }) =>
    api<ExecutiveDocument>("/pto/documents", { method: "POST", body: JSON.stringify(body) }),
  submit: (id: string) => api<ExecutiveDocument>(`/pto/documents/${id}/submit`, { method: "POST", body: "{}" }),
  decide: (id: string, decision: "approved" | "rejected", comment?: string) =>
    api<ExecutiveDocument>(`/pto/documents/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, comment }) }),
  completeness: (projectId: string) => api<Completeness>(`/pto/completeness?project_id=${projectId}`),
};
