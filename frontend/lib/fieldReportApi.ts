/*
 * Клиент backend-API «Мобильный ежедневный отчёт прораба» (рабочий контур).
 * Составление отчёта по объекту, работы/численность/техника/проблемы,
 * фото-доказательства (MinIO), отправка и проверка руководителем. Вызовы идут
 * через backend с JWT из хранилища сессии; базовый URL — из
 * NEXT_PUBLIC_API_BASE_URL. Без backend экраны показывают пустое состояние,
 * а не mock-данные. Секреты в коде не хранятся.
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

export interface Report {
  id: string; project_id: string; site_id: string | null; report_date: string;
  status: string; summary: string | null; reviewed_by_user_id: string | null;
  review_comment: string | null; submitted_at: string | null;
}
export interface WorkItem { id: string; work_type: string | null; task_id: string | null; actual_quantity: string; planned_quantity: string | null; verification_status: string; }
export interface Headcount { id: string; profession: string; count: number; }
export interface Equipment { id: string; name: string; equipment_type: string | null; count: number; hours: string; status: string; }
export interface Issue { id: string; issue_type: string; description: string; severity: string; }
export interface Evidence { id: string; file_id: string; kind: string; caption: string | null; original_name: string | null; }
export interface ReportDetail extends Report {
  weather_summary: string | null; work_completed: string | null; problems: string | null;
  plan_next_day: string | null; work_items: WorkItem[]; headcount: Headcount[];
  equipment: Equipment[]; issues: Issue[]; evidence: Evidence[];
}
export interface ReportSummary { draft: number; submitted: number; correction_required: number; approved: number; }

export const fieldReportApi = {
  summary: () => api<ReportSummary>("/field-reports/summary"),
  list: (projectId: string) => api<Report[]>(`/field-reports/projects/${projectId}`),
  get: (id: string) => api<ReportDetail>(`/field-reports/${id}`),
  create: (projectId: string, body: { report_date: string; site_id?: string; summary?: string; weather_summary?: string; plan_next_day?: string; client_request_id?: string }) =>
    // client_request_id обеспечивает идемпотентность повторной отправки формы (§18):
    // при нестабильной связи повтор с тем же ключом не создаёт дубль отчёта
    api<Report>(`/field-reports/projects/${projectId}`, { method: "POST", body: JSON.stringify(body) }),
  addWorkItem: (id: string, body: { work_type?: string; task_id?: string; planned_quantity?: number; actual_quantity: number }) =>
    api<WorkItem>(`/field-reports/${id}/work-items`, { method: "POST", body: JSON.stringify(body) }),
  addHeadcount: (id: string, body: { profession: string; count: number }) =>
    api<Headcount>(`/field-reports/${id}/headcount`, { method: "POST", body: JSON.stringify(body) }),
  addEquipment: (id: string, body: { name: string; hours?: number; status?: string }) =>
    api<Equipment>(`/field-reports/${id}/equipment`, { method: "POST", body: JSON.stringify(body) }),
  addIssue: (id: string, body: { issue_type: string; description: string; severity?: string }) =>
    api<Issue>(`/field-reports/${id}/issues`, { method: "POST", body: JSON.stringify(body) }),
  addEvidence: (id: string, body: { original_name: string; mime_type: string; content_base64: string; kind?: string; caption?: string }) =>
    api<Evidence>(`/field-reports/${id}/evidence`, { method: "POST", body: JSON.stringify(body) }),
  submit: (id: string) => api<Report>(`/field-reports/${id}/submit`, { method: "POST", body: "{}" }),
  review: (id: string, decision: "approved" | "rejected" | "correction_required", comment?: string) =>
    api<Report>(`/field-reports/${id}/review`, { method: "POST", body: JSON.stringify({ decision, comment }) }),
};
