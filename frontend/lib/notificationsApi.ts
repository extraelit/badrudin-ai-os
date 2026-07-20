/*
 * Клиент backend-API центра уведомлений (in-app). Персональные уведомления
 * пользователя: список, счётчик непрочитанных, отметка прочитанным. Вызовы идут через
 * backend с JWT из хранилища сессии; базовый URL — из NEXT_PUBLIC_API_BASE_URL. Без
 * backend экран показывает пустое состояние, а не mock-данные. Секреты в коде не
 * хранятся. Внешняя рассылка здесь не выполняется — только внутренний канал.
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

export interface Notification {
  id: string; title: string | null; message: string | null; priority: string;
  status: string; entity_type: string | null; entity_id: string | null;
  read_at: string | null; created_at: string;
}

export const notificationsApi = {
  list: (onlyUnread = false) => api<Notification[]>(`/notifications${onlyUnread ? "?only_unread=true" : ""}`),
  unreadCount: () => api<{ unread: number }>("/notifications/unread-count"),
  markRead: (id: string) => api<Notification>(`/notifications/${id}/read`, { method: "POST", body: "{}" }),
  markAllRead: () => api<{ marked: number }>("/notifications/read-all", { method: "POST", body: "{}" }),
};
