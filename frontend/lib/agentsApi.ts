/*
 * Клиент backend-API «Оркестратор ИИ-агентов» (governance-контур). Реестр
 * агентов, запуски, предложения агентов с обязательным человеческим утверждением
 * и применением через общий сервис. Вызовы идут через backend с JWT из хранилища
 * сессии; базовый URL — из NEXT_PUBLIC_API_BASE_URL. Без backend экраны показывают
 * пустое состояние, а не mock-данные. Секреты в коде не хранятся. Фактический
 * вызов модели выполняется отдельным утверждённым коннектором.
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

export interface Agent {
  id: string; code: string; name: string; agent_type: string | null; status: string;
  default_risk_level: string; requires_human_approval: boolean;
}
export interface Proposal {
  id: string; agent_id: string; run_id: string | null; proposal_type: string;
  title: string; summary: string | null; risk_level: string; status: string;
  project_id: string | null; applied_entity_type: string | null;
  applied_entity_id: string | null; decided_at: string | null;
}
export interface AgentSummary {
  agents_total: number; agents_active: number; proposals_pending: number;
  proposals_approved: number; proposals_rejected: number;
}

export const agentsApi = {
  summary: () => api<AgentSummary>("/agents/summary"),
  list: () => api<Agent[]>("/agents"),
  register: (body: { code: string; name: string; agent_type?: string }) =>
    api<Agent>("/agents", { method: "POST", body: JSON.stringify(body) }),
  setStatus: (id: string, status: string) =>
    api<Agent>(`/agents/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
  proposals: (status?: string) => api<Proposal[]>(`/agents/proposals${status ? `?status=${status}` : ""}`),
  addProposal: (agentId: string, body: { proposal_type: string; title: string; summary?: string; project_id?: string }) =>
    api<Proposal>(`/agents/${agentId}/proposals`, { method: "POST", body: JSON.stringify(body) }),
  review: (id: string, decision: "approved" | "rejected", comment?: string) =>
    api<Proposal>(`/agents/proposals/${id}/review`, { method: "POST", body: JSON.stringify({ decision, comment }) }),
  apply: (id: string) => api<Proposal>(`/agents/proposals/${id}/apply`, { method: "POST", body: "{}" }),
};
