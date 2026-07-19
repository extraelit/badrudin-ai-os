/*
 * Клиент backend-API «Техника, транспорт и инструмент» (рабочий контур). Реестр
 * техники, назначение/возврат, эксплуатация, топливо, техобслуживание, осмотры,
 * инструмент выдача/возврат. Вызовы идут через backend с JWT из хранилища сессии;
 * базовый URL — из NEXT_PUBLIC_API_BASE_URL. Без backend экраны показывают пустое
 * состояние, а не mock-данные. Секреты в коде не хранятся.
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

export interface Equipment {
  id: string; asset_number: string | null; name: string; asset_type: string;
  ownership_type: string; current_status: string; current_project_id: string | null;
  responsible_employee_id: string | null; odometer_value: string; engine_hours: string;
  fuel_type: string | null; next_service_at: string | null; next_inspection_at: string | null;
}
export interface Tool {
  id: string; inventory_number: string | null; name: string; tool_type: string | null;
  current_status: string; condition_status: string; current_employee_id: string | null;
}
export interface Maintenance {
  id: string; asset_type: string; asset_id: string; maintenance_type: string;
  status: string; priority: string; actual_cost: string | null;
}
export interface EquipmentSummary {
  equipment_total: number; equipment_available: number; equipment_assigned: number;
  equipment_under_repair: number; maintenance_open: number; service_due: number;
  tools_total: number; tools_issued: number;
}

export const equipmentApi = {
  summary: () => api<EquipmentSummary>("/equipment/summary"),
  list: () => api<Equipment[]>("/equipment"),
  register: (body: { name: string; asset_type?: string; fuel_type?: string }) =>
    api<Equipment>("/equipment", { method: "POST", body: JSON.stringify(body) }),
  assign: (id: string, body: { project_id?: string; responsible_employee_id?: string }) =>
    api<unknown>(`/equipment/${id}/assign`, { method: "POST", body: JSON.stringify(body) }),
  returnEquipment: (id: string) => api<Equipment>(`/equipment/${id}/return`, { method: "POST", body: "{}" }),
  logUsage: (id: string, body: { usage_date: string; engine_hours_end?: number; odometer_end?: number; downtime_hours?: number; fuel_consumed?: number }) =>
    api<unknown>(`/equipment/${id}/usage`, { method: "POST", body: JSON.stringify(body) }),
  inspect: (id: string, body: { inspection_type?: string; result?: string; operation_allowed?: boolean; defects?: string }) =>
    api<unknown>(`/equipment/${id}/inspection`, { method: "POST", body: JSON.stringify(body) }),
  listMaintenance: () => api<Maintenance[]>("/equipment/maintenance/orders"),
  openMaintenance: (body: { asset_type: string; asset_id: string; maintenance_type?: string; problem_description?: string }) =>
    api<Maintenance>("/equipment/maintenance", { method: "POST", body: JSON.stringify(body) }),
  completeMaintenance: (id: string, body: { actual_cost?: number }) =>
    api<Maintenance>(`/equipment/maintenance/${id}/complete`, { method: "POST", body: JSON.stringify(body) }),
  recordFuel: (body: { transaction_type: string; fuel_type?: string; quantity: number; unit_price?: number; equipment_id?: string; project_id?: string }) =>
    api<unknown>("/equipment/fuel", { method: "POST", body: JSON.stringify(body) }),
  listTools: () => api<Tool[]>("/equipment/tools/list"),
  registerTool: (body: { name: string; tool_type?: string }) =>
    api<Tool>("/equipment/tools", { method: "POST", body: JSON.stringify(body) }),
  issueTool: (id: string, body: { employee_id: string; project_id?: string; condition_at_issue?: string }) =>
    api<unknown>(`/equipment/tools/${id}/issue`, { method: "POST", body: JSON.stringify(body) }),
  returnTool: (id: string, body: { condition_at_return?: string }) =>
    api<Tool>(`/equipment/tools/${id}/return`, { method: "POST", body: JSON.stringify(body) }),
};
