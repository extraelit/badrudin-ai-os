/*
 * Клиент backend-API «Масштабирование интеграций» — внутренний контур. Реестр
 * коннекторов и очередь исходящих сообщений (черновики на утверждение; отправка
 * не производится, секреты не хранятся). Вызовы идут через backend с JWT из
 * хранилища сессии; базовый URL — из NEXT_PUBLIC_API_BASE_URL. Без backend экраны
 * показывают пустое состояние, а не mock-данные. Секреты в коде не хранятся.
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

export interface Connector {
  id: string; code: string; name: string; channel: string; provider: string | null;
  config_summary: string | null; status: string; credentials_configured_externally: boolean;
}
export interface Outbound {
  id: string; channel: string; subject: string | null; body_text: string | null;
  recipient: string | null; status: string; risk_level: string; project_id: string | null;
  connector_id: string | null; approval_id: string | null; approved_at: string | null;
}
export interface IntegrationSummary {
  connectors_total: number; connectors_configured: number; outbound_draft: number;
  outbound_pending: number; outbound_approved: number;
}

export const integrationApi = {
  summary: () => api<IntegrationSummary>("/integrations/summary"),
  listConnectors: () => api<Connector[]>("/integrations/connectors"),
  registerConnector: (body: { code: string; name: string; channel: string; provider?: string }) =>
    api<Connector>("/integrations/connectors", { method: "POST", body: JSON.stringify(body) }),
  setConnectorStatus: (id: string, status: string, credentials_configured_externally?: boolean) =>
    api<Connector>(`/integrations/connectors/${id}/status`, { method: "POST", body: JSON.stringify({ status, credentials_configured_externally }) }),
  listOutbound: (status?: string) => api<Outbound[]>(`/integrations/outbound${status ? `?status=${status}` : ""}`),
  createDraft: (body: { channel: string; subject?: string; body_text?: string; recipient?: string; project_id?: string }) =>
    api<Outbound>("/integrations/outbound", { method: "POST", body: JSON.stringify(body) }),
  submit: (id: string) => api<Outbound>(`/integrations/outbound/${id}/submit`, { method: "POST", body: "{}" }),
  decide: (id: string, decision: "approved" | "rejected", comment?: string) =>
    api<Outbound>(`/integrations/outbound/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, comment }) }),
  cancel: (id: string, reason: string) =>
    api<Outbound>(`/integrations/outbound/${id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }),
};
