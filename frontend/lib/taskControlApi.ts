/*
 * Клиент backend-API «Контроль исполнения поручений» (рабочий контур). Доска
 * контроля по статусам, препятствия, вопросы/ответы, эскалация, возврат на
 * доработку, лента активности и уведомления. Вызовы идут через backend с JWT из
 * хранилища сессии; базовый URL — из NEXT_PUBLIC_API_BASE_URL. Без backend
 * экраны показывают пустое состояние, а не mock-данные. Секреты в коде не хранятся.
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

export interface TaskCard {
  id: string; project_id: string | null; title: string; status: string;
  priority: string; risk_level: string; due_at: string | null; overdue: boolean;
  blocked_reason: string | null; escalation_level: number; owner_employee_id: string | null;
}
export interface Board {
  overdue: TaskCard[]; blocked: TaskCard[]; waiting_for_information: TaskCard[];
  in_progress: TaskCard[]; pending_review: TaskCard[]; returned_for_revision: TaskCard[];
}
export interface Activity {
  id: string; update_type: string; message: string | null; blocker_category: string | null;
  progress_percent: number | null; created_at: string;
}
export interface Notification {
  id: string; title: string | null; message: string | null; entity_type: string | null;
  entity_id: string | null; priority: string; status: string; read_at: string | null; created_at: string;
}

export const taskControlApi = {
  board: () => api<Board>("/task-control/board"),
  activity: (taskId: string) => api<Activity[]>(`/task-control/tasks/${taskId}/activity`),
  blocker: (taskId: string, category: string, message: string) =>
    api<TaskCard>(`/task-control/tasks/${taskId}/blocker`, { method: "POST", body: JSON.stringify({ category, message }) }),
  resolveBlocker: (taskId: string, message?: string) =>
    api<TaskCard>(`/task-control/tasks/${taskId}/resolve-blocker`, { method: "POST", body: JSON.stringify({ message }) }),
  question: (taskId: string, message: string) =>
    api<TaskCard>(`/task-control/tasks/${taskId}/question`, { method: "POST", body: JSON.stringify({ message }) }),
  answer: (taskId: string, message: string) =>
    api<TaskCard>(`/task-control/tasks/${taskId}/answer`, { method: "POST", body: JSON.stringify({ message }) }),
  escalate: (taskId: string, message?: string) =>
    api<TaskCard>(`/task-control/tasks/${taskId}/escalate`, { method: "POST", body: JSON.stringify({ message }) }),
  returnForRevision: (taskId: string, message: string) =>
    api<TaskCard>(`/task-control/tasks/${taskId}/return`, { method: "POST", body: JSON.stringify({ message }) }),
  comment: (taskId: string, message: string) =>
    api<Activity>(`/task-control/tasks/${taskId}/comment`, { method: "POST", body: JSON.stringify({ message }) }),
  notifications: (unreadOnly = false) =>
    api<Notification[]>(`/task-control/notifications${unreadOnly ? "?unread_only=true" : ""}`),
  readNotification: (id: string) =>
    api<Notification>(`/task-control/notifications/${id}/read`, { method: "POST", body: "{}" }),
};
