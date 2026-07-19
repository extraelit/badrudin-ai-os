/*
 * Клиент backend-API «Управленческие сводки руководителю» (рабочий контур).
 * Утренняя и вечерняя сводка по организации на реальных данных. Вызовы идут
 * через backend с JWT из хранилища сессии; базовый URL — из
 * NEXT_PUBLIC_API_BASE_URL. Без backend экраны показывают пустое состояние,
 * а не mock-данные. Секреты в коде не хранятся.
 */
import { getToken } from "./authApi";

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) || "";

async function api<T>(path: string): Promise<T> {
  if (!API_BASE) throw new Error("Backend не настроен");
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()) as T;
}

export interface ApprovalRef { id: string; entity_type: string; approval_type: string; entity_id: string; }
export interface TaskRef { id: string; title: string; status: string; risk_level: string; due_at: string | null; escalation_level: number; }
export interface Digest {
  kind: string;
  generated_at: string;
  period_label: string;
  projects_active: number;
  tasks: Record<string, number>;
  approvals_pending: number;
  approvals: ApprovalRef[];
  finance: Record<string, number>;
  procurement: Record<string, number>;
  warehouse: Record<string, string | number>;
  field_reports: Record<string, number>;
  accountable: Record<string, string | number>;
  risks: Record<string, number>;
  top_overdue: TaskRef[];
}

export const managementApi = {
  digest: (kind: "morning" | "evening") => api<Digest>(`/management/digest?kind=${kind}`),
};
