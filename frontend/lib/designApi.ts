/*
 * Клиент backend-API модуля «Проектирование и дизайн».
 *
 * Вызовы идут через backend — единственную точку доступа к данным. Базовый URL —
 * из переменной окружения, токен (если есть) — из хранилища сессии. Секреты в
 * коде не хранятся. В демо-режиме (нет backend/токена) вызовы мягко завершаются
 * ошибкой, и интерфейс использует mock-данные без изменения дизайна.
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

export interface ApiDesignOverview {
  project_id: string;
  disciplines_total: number;
  disciplines_issued: number;
  avg_completion: number;
  brief_status: string | null;
  concepts_total: number;
  specifications_total: number;
  issues_open: number;
  issues_critical: number;
}

export interface ApiDiscipline {
  id: string;
  project_id: string;
  code: string | null;
  name: string;
  discipline_type: string;
  responsible_employee_id: string | null;
  due_date: string | null;
  completion_percent: number;
  gip_status: string;
  status: string;
}

export const designApi = {
  getOverview: (projectId: string) =>
    api<ApiDesignOverview>(`/design/projects/${projectId}/overview`),
  listDisciplines: (projectId: string) =>
    api<ApiDiscipline[]>(`/design/projects/${projectId}/disciplines`),
  listIssues: (projectId: string) =>
    api<unknown[]>(`/design/projects/${projectId}/issues`),
  listSpecifications: (projectId: string) =>
    api<unknown[]>(`/design/projects/${projectId}/specifications`),
  checkRealizability: (specId: string) =>
    api<unknown>(`/design/specifications/${specId}/realizability`, { method: "POST" }),
  requestRelease: (disciplineId: string, documentId: string) =>
    api<{ approval_id: string; risk_level: string }>(
      `/design/disciplines/${disciplineId}/request-release`,
      { method: "POST", body: JSON.stringify({ document_id: documentId }) }
    ),
  listSuppliers: () => api<unknown[]>(`/design/suppliers`),
};
