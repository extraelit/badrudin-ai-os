/*
 * Клиент backend-API модуля «Подотчётные средства».
 * Рабочий контур: вызовы идут через backend с JWT из хранилища сессии; базовый
 * URL — из NEXT_PUBLIC_API_BASE_URL. Без backend экраны показывают пустое
 * состояние, а не mock-данные.
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

export interface Advance {
  id: string; employee_id: string; purpose: string; amount_issued: string;
  amount_spent_confirmed: string; amount_returned: string; amount_reimbursable: string;
  balance_amount: string; currency_code: string; status: string; risk_level: string;
  report_due_at: string | null; approval_id: string | null;
}
export interface Expense {
  id: string; advance_id: string; expense_category_id: string; amount: string;
  expense_date: string; description: string; payment_method: string;
  receipt_required: boolean; document_status: string; verification_status: string;
}
export interface Category { id: string; code: string | null; name: string; requires_receipt: boolean; requires_preapproval: boolean; default_limit: string | null; }
export interface AccSummary { advances_open: number; advances_overdue: number; total_issued: string; total_spent: string; total_outstanding: string; reports_pending: number; }
export interface AccReport { id: string; advance_id: string; total_expenses_submitted: string; total_expenses_approved: string; amount_to_return: string; amount_to_reimburse: string; status: string; }

export const accountableApi = {
  summary: () => api<AccSummary>("/accountable/summary"),
  listCategories: () => api<Category[]>("/accountable/expense-categories"),
  listAdvances: () => api<Advance[]>("/accountable/advances"),
  createAdvance: (body: Record<string, unknown>) =>
    api<Advance>("/accountable/advances", { method: "POST", body: JSON.stringify(body) }),
  requestApproval: (id: string) => api<Advance>(`/accountable/advances/${id}/request-approval`, { method: "POST", body: "{}" }),
  decide: (id: string, decision: "approved" | "rejected", mfaCode?: string) =>
    api<Advance>(`/accountable/advances/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, mfa_code: mfaCode }) }),
  issue: (id: string) => api<Advance>(`/accountable/advances/${id}/issue`, { method: "POST", body: "{}" }),
  listExpenses: (id: string) => api<Expense[]>(`/accountable/advances/${id}/expenses`),
  addExpense: (id: string, body: Record<string, unknown>) =>
    api<Expense>(`/accountable/advances/${id}/expenses`, { method: "POST", body: JSON.stringify(body) }),
  attachReceipt: (expenseId: string, body: Record<string, unknown>) =>
    api<unknown>(`/accountable/expenses/${expenseId}/documents`, { method: "POST", body: JSON.stringify(body) }),
  verifyExpense: (expenseId: string, decision: "approved" | "rejected", reason?: string) =>
    api<Expense>(`/accountable/expenses/${expenseId}/verify`, { method: "POST", body: JSON.stringify({ decision, reason }) }),
  submitReport: (id: string) => api<AccReport>(`/accountable/advances/${id}/report`, { method: "POST", body: "{}" }),
  reviewReport: (reportId: string, decision: "approved" | "correction_required") =>
    api<AccReport>(`/accountable/reports/${reportId}/review`, { method: "POST", body: JSON.stringify({ decision }) }),
  settle: (id: string, settlementType: "return" | "reimbursement", amount: number) =>
    api<unknown>(`/accountable/advances/${id}/settlements`, { method: "POST", body: JSON.stringify({ settlement_type: settlementType, amount }) }),
};
