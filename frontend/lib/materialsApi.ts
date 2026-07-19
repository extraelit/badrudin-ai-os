/*
 * Клиент backend-API «Заявки и выдача материалов» (рабочий контур модуля
 * снабжения). Все вызовы идут через backend с JWT из хранилища сессии; базовый
 * URL — из NEXT_PUBLIC_API_BASE_URL. Без backend экраны показывают пустое
 * состояние, а не mock-данные. Секреты в коде не хранятся.
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

export interface Warehouse { id: string; name: string; code: string | null; site_id: string | null; status: string; }
export interface MaterialRequest {
  id: string; project_id: string; site_id: string | null; task_id: string | null;
  number: string | null; status: string; priority: string; is_critical: boolean;
  risk_level: string; needed_by: string | null; lines_count: number; approval_id: string | null;
}
export interface RequestLine {
  id: string; material_id: string | null; description: string | null; quantity: string;
  reserved_quantity: string; issued_quantity: string; returned_quantity: string; status: string;
}
export interface RequestDetail extends MaterialRequest {
  reason: string | null; rejection_reason: string | null; lines: RequestLine[];
}
export interface IssueResult {
  id: string; warehouse_id: string; material_request_id: string | null; number: string | null;
  status: string; acknowledgement_status: string; acknowledged_by: string | null; lines_count: number;
}
export interface ReturnResult {
  id: string; material_id: string; quantity: string; return_type: string; status: string;
  material_request_id: string | null; confirmed_by: string | null;
}

export interface NewRequest {
  site_id?: string; task_id?: string; number?: string; priority?: string;
  is_critical?: boolean; needed_by?: string;
  lines: { material_id?: string; description?: string; quantity: number }[];
}

export const materialsApi = {
  listWarehouses: () => api<Warehouse[]>("/procurement/warehouses"),
  listRequests: (projectId: string) => api<MaterialRequest[]>(`/procurement/projects/${projectId}/requests`),
  getRequest: (id: string) => api<RequestDetail>(`/procurement/requests/${id}`),
  createRequest: (projectId: string, body: NewRequest) =>
    api<MaterialRequest>(`/procurement/projects/${projectId}/requests`, { method: "POST", body: JSON.stringify(body) }),
  submit: (id: string) => api<MaterialRequest>(`/procurement/requests/${id}/submit`, { method: "POST", body: "{}" }),
  requestApproval: (id: string) => api<MaterialRequest>(`/procurement/requests/${id}/request-approval`, { method: "POST", body: "{}" }),
  decide: (id: string, decision: "approved" | "rejected", comment?: string, mfaCode?: string) =>
    api<MaterialRequest>(`/procurement/requests/${id}/decision`, {
      method: "POST", body: JSON.stringify({ decision, comment, mfa_code: mfaCode }),
    }),
  reserve: (id: string, warehouseId: string) =>
    api<MaterialRequest>(`/procurement/requests/${id}/reserve`, { method: "POST", body: JSON.stringify({ warehouse_id: warehouseId }) }),
  issue: (id: string, body: { warehouse_id: string; issued_to?: string; items: { request_line_id: string; quantity: number }[] }) =>
    api<IssueResult>(`/procurement/requests/${id}/issue`, { method: "POST", body: JSON.stringify(body) }),
  acknowledge: (issueId: string, confirmed: boolean, reason?: string) =>
    api<IssueResult>(`/procurement/issues/${issueId}/acknowledge`, { method: "POST", body: JSON.stringify({ confirmed, reason }) }),
  returnFromRequest: (id: string, body: { warehouse_id: string; material_id: string; quantity: number; request_line_id?: string; issue_id?: string; reason?: string }) =>
    api<ReturnResult>(`/procurement/requests/${id}/return`, { method: "POST", body: JSON.stringify(body) }),
  confirmReturn: (returnId: string) =>
    api<ReturnResult>(`/procurement/returns/${returnId}/confirm`, { method: "POST", body: "{}" }),
};
