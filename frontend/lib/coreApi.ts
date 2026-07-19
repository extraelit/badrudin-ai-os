/*
 * Клиент backend-API рабочего ядра (проекты, объекты, задачи, согласования,
 * ежедневные отчёты, сводка). Все вызовы идут через backend с JWT из хранилища
 * сессии; базовый URL — из NEXT_PUBLIC_API_BASE_URL. Это рабочий контур: без
 * backend экраны показывают пустое состояние, а не mock-данные.
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

export interface Project { id: string; name: string; project_type: string; code: string | null; status: string; completion_percent: number; }
export interface Site { id: string; project_id: string; name: string; address: string | null; code: string | null; status: string; }
export interface Task { id: string; project_id: string; site_id: string | null; title: string; description: string | null; status: string; priority: string; risk_level: string; due_at: string | null; owner_employee_id: string | null; }
export interface ApprovalItem { id: string; entity_type: string; entity_id: string; approval_type: string; status: string; title: string | null; }
export interface DailyReport { id: string; project_id: string; site_id: string | null; report_date: string; workers_count: number | null; summary: string | null; status: string; }
export interface Dashboard { projects: number; sites: number; tasks_open: number; tasks_overdue: number; tasks_completed: number; approvals_pending: number; reports_today: number; }

export const coreApi = {
  dashboard: () => api<Dashboard>("/core/dashboard"),

  listProjects: () => api<Project[]>("/core/projects"),
  createProject: (body: { name: string; project_type?: string; code?: string; description?: string }) =>
    api<Project>("/core/projects", { method: "POST", body: JSON.stringify(body) }),

  listSites: (projectId: string) => api<Site[]>(`/core/projects/${projectId}/sites`),
  createSite: (projectId: string, body: { name: string; address?: string; code?: string }) =>
    api<Site>(`/core/projects/${projectId}/sites`, { method: "POST", body: JSON.stringify(body) }),

  listTasks: (projectId: string) => api<Task[]>(`/core/projects/${projectId}/tasks`),
  createTask: (projectId: string, body: { title: string; description?: string; site_id?: string }) =>
    api<Task>(`/core/projects/${projectId}/tasks`, { method: "POST", body: JSON.stringify(body) }),
  taskAction: (taskId: string, action: "submit" | "accept" | "complete") =>
    api<Task>(`/core/tasks/${taskId}/${action}`, { method: "POST", body: JSON.stringify({}) }),
  assignTask: (taskId: string, employeeId: string) =>
    api<Task>(`/core/tasks/${taskId}/assign`, { method: "POST", body: JSON.stringify({ employee_id: employeeId }) }),
  taskProgress: (taskId: string, progress: number) =>
    api<Task>(`/core/tasks/${taskId}/progress`, { method: "POST", body: JSON.stringify({ progress_percent: progress }) }),

  listApprovals: () => api<ApprovalItem[]>("/core/approvals"),
  decideApproval: (approvalId: string, decision: "approved" | "rejected", comment?: string) =>
    api<ApprovalItem>(`/core/approvals/${approvalId}/decision`, { method: "POST", body: JSON.stringify({ decision, comment }) }),

  listReports: (projectId: string) => api<DailyReport[]>(`/core/projects/${projectId}/daily-reports`),
  createReport: (projectId: string, body: { report_date: string; site_id?: string; workers_count?: number; summary?: string }) =>
    api<DailyReport>(`/core/projects/${projectId}/daily-reports`, { method: "POST", body: JSON.stringify(body) }),
  submitReport: (reportId: string) =>
    api<DailyReport>(`/core/daily-reports/${reportId}/submit`, { method: "POST", body: JSON.stringify({}) }),
};
