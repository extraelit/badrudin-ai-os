/*
 * Клиент универсальных вложений: прикрепление файлов к любой сущности, список,
 * скачивание, архивирование. Через backend с JWT; базовый URL —
 * NEXT_PUBLIC_API_BASE_URL. Права проверяются на сервере (attachment.view/manage).
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
      /* тело не JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export interface AttachmentItem {
  id: string;
  file_id: string;
  entity_type: string;
  entity_id: string;
  project_id: string | null;
  attachment_type: string;
  description: string | null;
  original_name: string;
  mime_type: string | null;
  size_bytes: number | null;
  checksum_sha256: string | null;
  version: number;
  is_current: boolean;
  is_archived: boolean;
  uploaded_by: string | null;
  created_at: string;
}

/** Читает File как base64 (без префикса data:) для передачи в API. */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",")[1]! : result);
    };
    reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
    reader.readAsDataURL(file);
  });
}

export const attachmentApi = {
  list: (entityType: string, entityId: string, includeArchived = false) =>
    api<AttachmentItem[]>(
      `/attachments/?entity_type=${encodeURIComponent(entityType)}` +
        `&entity_id=${encodeURIComponent(entityId)}&include_archived=${includeArchived}`,
    ),

  attach: (body: {
    entity_type: string;
    entity_id: string;
    original_name: string;
    content_base64: string;
    mime_type?: string;
    attachment_type?: string;
    description?: string;
    project_id?: string;
    replaces_id?: string;
  }) => api<AttachmentItem>("/attachments/", { method: "POST", body: JSON.stringify(body) }),

  archive: (id: string, reason: string) =>
    api<AttachmentItem>(`/attachments/${id}/archive`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  /** URL для скачивания (с токеном в query не передаём — используем fetch с заголовком). */
  downloadUrl: (id: string) => `${API_BASE}/attachments/${id}/download`,
};
