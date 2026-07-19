/*
 * Клиент backend-API «Складской учёт и остатки» (рабочий контур). Остатки,
 * журнал движений, складская карточка, резервы, места хранения. Вызовы идут
 * через backend с JWT из хранилища сессии; базовый URL — из
 * NEXT_PUBLIC_API_BASE_URL. Без backend экраны показывают пустое состояние,
 * а не mock-данные. Секреты в коде не хранятся.
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

export interface StockSummary {
  positions: number; warehouses_with_stock: number; total_value: string;
  reserved_positions: number; low_stock: number; negative_stock: number;
}
export interface StockRow {
  warehouse_id: string; material_id: string; material_name: string | null;
  location_id: string | null; quantity: string; reserved_quantity: string;
  available_quantity: string; minimum_quantity: string; average_unit_cost: string;
  currency: string; low: boolean;
}
export interface LedgerRow {
  id: string; warehouse_id: string; material_id: string; material_name: string | null;
  transaction_type: string; quantity: string; unit_cost: string;
  source_type: string | null; source_id: string | null; occurred_at: string | null;
}
export interface Reservation {
  id: string; warehouse_id: string | null; material_id: string; material_name: string | null;
  quantity: string; status: string; reserved_until: string | null; reason: string | null;
  purchase_order_id: string | null; material_request_id: string | null;
}
export interface WarehouseRef { id: string; name: string; code: string | null; site_id: string | null; status: string; }

export const inventoryApi = {
  listWarehouses: () => api<WarehouseRef[]>("/procurement/warehouses"),
  summary: () => api<StockSummary>("/warehouse/summary"),
  stock: (warehouseId?: string, lowOnly = false) =>
    api<StockRow[]>(`/warehouse/stock?${new URLSearchParams({ ...(warehouseId ? { warehouse_id: warehouseId } : {}), ...(lowOnly ? { low_only: "true" } : {}) })}`),
  ledger: (warehouseId?: string) =>
    api<LedgerRow[]>(`/warehouse/ledger${warehouseId ? `?warehouse_id=${warehouseId}` : ""}`),
  reservations: (warehouseId?: string, status?: string) =>
    api<Reservation[]>(`/warehouse/reservations?${new URLSearchParams({ ...(warehouseId ? { warehouse_id: warehouseId } : {}), ...(status ? { status } : {}) })}`),
  reserve: (body: { warehouse_id: string; material_id: string; quantity: number; reason?: string }) =>
    api<Reservation>("/warehouse/reservations", { method: "POST", body: JSON.stringify(body) }),
  release: (id: string) => api<Reservation>(`/warehouse/reservations/${id}/release`, { method: "POST", body: "{}" }),
  setMinQuantity: (body: { warehouse_id: string; material_id: string; minimum_quantity: number }) =>
    api<StockRow>("/warehouse/stock/min-quantity", { method: "POST", body: JSON.stringify(body) }),
};
