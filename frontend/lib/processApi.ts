/*
 * Клиент процессного ядра: процессы (жизненный цикл), Evidence Gate,
 * руководительские панели, ежедневный отчёт (ИИ-черновик), качество.
 * Все вызовы идут через backend с JWT; базовый URL — из NEXT_PUBLIC_API_BASE_URL.
 * Действия скрываются в интерфейсе по правам пользователя, но проверяются на сервере.
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
  if (!res.ok) {
    let detail = `API ${res.status}`;
    try {
      const body = (await res.json()) as { error?: { message?: string }; detail?: string };
      detail = body?.error?.message || body?.detail || detail;
    } catch {
      /* тело не JSON — оставляем код статуса */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export interface WorkflowProcess {
  id: string;
  project_id: string | null;
  process_kind: string;
  title: string;
  description: string | null;
  risk_level: string;
  status: string;
  overdue: boolean;
  priority: string;
  primary_executor_id: string | null;
  responsible_manager_id: string | null;
  due_at: string | null;
  accepted_at: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  reschedule_count: number;
  executor_comment: string | null;
  reviewer_comment: string | null;
}

export interface ManagerOverview {
  processes_total: number;
  by_status: Record<string, number>;
  overdue: number;
  pending_approval: number;
  submitted_for_review: number;
  blocked: number;
  evidence_exceptions_pending: number;
  quality_pending_finalization: number;
}

export interface OverdueItem {
  id: string;
  title: string;
  process_kind: string;
  risk_level: string;
  status: string;
  due_at: string | null;
  primary_executor_id: string | null;
  responsible_manager_id: string | null;
}

export interface ExceptionItem {
  id: string;
  process_id: string;
  evidence_type: string;
  reason: string;
  status: string;
}

export const processApi = {
  list: () => api<WorkflowProcess[]>("/processes/"),
  get: (id: string) => api<WorkflowProcess>(`/processes/${id}`),
  create: (body: {
    process_kind: string;
    title: string;
    description?: string;
    project_id?: string;
    risk_level?: string;
    due_at?: string;
  }) => api<WorkflowProcess>("/processes/", { method: "POST", body: JSON.stringify(body) }),

  submitApproval: (id: string) =>
    api<WorkflowProcess>(`/processes/${id}/submit-approval`, { method: "POST", body: "{}" }),
  approve: (id: string) =>
    api<WorkflowProcess>(`/processes/${id}/approve`, { method: "POST", body: "{}" }),
  assign: (id: string, executor_id: string, due_at?: string) =>
    api<WorkflowProcess>(`/processes/${id}/assign`, {
      method: "POST",
      body: JSON.stringify({ executor_id, due_at }),
    }),
  accept: (id: string) =>
    api<WorkflowProcess>(`/processes/${id}/accept`, { method: "POST", body: "{}" }),
  start: (id: string) =>
    api<WorkflowProcess>(`/processes/${id}/start`, { method: "POST", body: "{}" }),
  submitReview: (id: string, executor_comment?: string) =>
    api<WorkflowProcess>(`/processes/${id}/submit-review`, {
      method: "POST",
      body: JSON.stringify({ executor_comment }),
    }),
  review: (id: string, decision: "completed" | "revision_required", comment?: string) =>
    api<WorkflowProcess>(`/processes/${id}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, comment }),
    }),
  reschedule: (id: string, new_due_at: string, reason: string, approved_by_manager: boolean) =>
    api<WorkflowProcess>(`/processes/${id}/reschedule`, {
      method: "POST",
      body: JSON.stringify({ new_due_at, reason, approved_by_manager }),
    }),

  managerOverview: () => api<ManagerOverview>("/manager/overview"),
  overdue: () => api<OverdueItem[]>("/manager/overdue"),
  exceptions: () => api<ExceptionItem[]>("/manager/exceptions"),
  escalateOverdue: () =>
    api<{ notifications_created: number }>("/manager/escalate-overdue", {
      method: "POST",
      body: "{}",
    }),
};
