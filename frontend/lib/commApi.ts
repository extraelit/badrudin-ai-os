/*
 * Клиент центра коммуникаций: сообщения (жизненный цикл), контакты, шаблоны,
 * каналы, журнал доставки. Через backend с JWT; базовый URL —
 * NEXT_PUBLIC_API_BASE_URL. Реальная отправка на сервере выключена (sandbox).
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

export interface CommMessage {
  id: string;
  direction: string;
  channel: string;
  subject: string | null;
  body_text: string | null;
  status: string;
  external_id: string | null;
  error_reason: string | null;
  attempts: number;
  scheduled_at: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface CommRecipient {
  id: string;
  address: string;
  kind: string;
  status: string;
  external_id: string | null;
  error_reason: string | null;
}

export interface CommContact {
  id: string;
  display_name: string;
  email: string | null;
  phone: string | null;
  telegram: string | null;
  whatsapp: string | null;
  instagram: string | null;
  consent: boolean;
  stop_listed: boolean;
}

export interface CommTemplate {
  id: string;
  code: string;
  name: string;
  channel: string;
  subject: string | null;
  body_text: string;
  is_approved: boolean;
}

export interface CommChannel {
  id: string;
  code: string;
  name: string;
  channel: string;
  provider: string | null;
  status: string;
  credentials_configured_externally: boolean;
}

export interface DeliveryEvent {
  id: string;
  event: string;
  detail: string | null;
  external_id: string | null;
  recipient_id: string | null;
  occurred_at: string;
}

export const commApi = {
  inbox: () => api<CommMessage[]>("/communications/inbox"),
  outbox: () => api<CommMessage[]>("/communications/outbox"),
  drafts: () => api<CommMessage[]>("/communications/drafts"),
  channels: () => api<CommChannel[]>("/communications/channels"),
  templates: () => api<CommTemplate[]>("/communications/templates"),
  contacts: () => api<CommContact[]>("/communications/contacts"),
  message: (id: string) =>
    api<CommMessage & { recipients: CommRecipient[] }>(`/communications/messages/${id}`),
  deliveryLog: (id: string) =>
    api<DeliveryEvent[]>(`/communications/messages/${id}/delivery-log`),

  createMessage: (body: {
    channel: string;
    subject?: string;
    body_text?: string;
    project_id?: string;
    recipients: { address: string; contact_id?: string; kind?: string }[];
  }) => api<CommMessage>("/communications/messages", { method: "POST", body: JSON.stringify(body) }),
  submitApproval: (id: string) =>
    api<CommMessage>(`/communications/messages/${id}/submit-approval`, { method: "POST", body: "{}" }),
  approve: (id: string) =>
    api<CommMessage>(`/communications/messages/${id}/approve`, { method: "POST", body: "{}" }),
  send: (id: string) =>
    api<CommMessage>(`/communications/messages/${id}/send`, { method: "POST", body: "{}" }),
  retry: (id: string) =>
    api<CommMessage>(`/communications/messages/${id}/retry`, { method: "POST", body: "{}" }),
  cancel: (id: string, reason?: string) =>
    api<CommMessage>(`/communications/messages/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  createContact: (body: Record<string, unknown>) =>
    api<CommContact>("/communications/contacts", { method: "POST", body: JSON.stringify(body) }),
  createTemplate: (body: Record<string, unknown>) =>
    api<CommTemplate>("/communications/templates", { method: "POST", body: JSON.stringify(body) }),
};
