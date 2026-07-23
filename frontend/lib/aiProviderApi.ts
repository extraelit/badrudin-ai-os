/*
 * Клиент слоя ИИ-провайдеров (Настройки → ИИ-провайдеры). Ключи никогда не
 * передаются — только маскированный индикатор. Реальные вызовы ИИ по умолчанию
 * выключены (эхо-режим). Права проверяются на сервере (ai.provider.view/manage).
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

export interface AIProvider {
  id: string;
  code: string;
  name: string;
  enabled: boolean;
  base_url: string | null;
  default_model: string | null;
  credentials_configured_externally: boolean;
  key_hint: string;
  notes: string | null;
}

export interface AIUsage {
  id: string;
  agent_id: string | null;
  provider_id: string | null;
  model: string | null;
  tokens_in: number;
  tokens_out: number;
  cost: number;
  request_id: string | null;
  created_at: string;
}

export interface AIHealth {
  provider_id: string;
  status: string;
  checked_at: string;
  detail: string | null;
}

export interface AgentAssignment {
  id: string;
  agent_id: string;
  primary_provider_id: string | null;
  primary_model: string | null;
  fallback_provider_id: string | null;
  fallback_model: string | null;
  max_tokens: number | null;
}

export const aiProviderApi = {
  list: () => api<AIProvider[]>("/ai-providers/"),
  create: (body: { code: string; name: string; default_model?: string; base_url?: string }) =>
    api<AIProvider>("/ai-providers/", { method: "POST", body: JSON.stringify(body) }),
  setEnabled: (id: string, enabled: boolean) =>
    api<AIProvider>(`/ai-providers/${id}/enable`, { method: "POST", body: JSON.stringify({ enabled }) }),
  health: (id: string) =>
    api<AIHealth>(`/ai-providers/${id}/health`, { method: "POST", body: "{}" }),
  usage: () => api<AIUsage[]>("/ai-providers/usage"),
  getAssignment: (agentId: string) =>
    api<AgentAssignment | null>(`/ai-providers/agents/${agentId}/assignment`),
  setAssignment: (agentId: string, body: Record<string, unknown>) =>
    api<AgentAssignment>(`/ai-providers/agents/${agentId}/assignment`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};

export interface AgentRef { id: string; name: string; code?: string }
export const agentsList = () => api<AgentRef[]>("/agents");
