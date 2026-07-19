/*
 * Демонстрационные (mock) данные модуля «Финансы и бюджеты».
 * Все данные вымышленные, только для показа интерфейса. Реальных ПДн, секретов
 * и подключения к production нет.
 *
 * Переиспользование канона (DATABASE.md разделы 16.2–16.4): бюджет проекта →
 * budgets/budget_lines; обязательства → purchase_orders + расходные contracts +
 * ручные financial_commitments; факт → полученные заказы + утверждённый
 * payroll_drafts; план → утверждённая estimates. Согласования → approvals
 * (R3/R4 + MFA); аудит → audit_events. Подотчётные средства вынесены в
 * отдельный будущий модуль.
 */
import type { IconName } from "./icons";

export type Tone = "emerald" | "amber" | "red" | "gray" | "navy";
export type RiskLevel = "R0" | "R1" | "R2" | "R3" | "R4";

export interface FinKpi {
  label: string;
  value: string;
  trend?: string;
  up?: boolean;
  icon: IconName;
  tone: string;
  foot?: string;
}

export const finKpis: FinKpi[] = [
  { label: "Утверждённый бюджет", value: "48,6 млн ₽", trend: "3 проекта", up: true, icon: "finance", tone: "navy", foot: "по портфелю" },
  { label: "Обязательства", value: "21,3 млн ₽", trend: "заказы+договоры", up: true, icon: "procurement", tone: "amber", foot: "не оплачено" },
  { label: "Фактические затраты", value: "18,9 млн ₽", trend: "+2,4 млн", up: true, icon: "reports", tone: "emerald", foot: "освоено" },
  { label: "Прогноз к бюджету", value: "−1,2 млн ₽", trend: "перерасход риск", up: false, icon: "approvals", tone: "red", foot: "прогноз−бюджет" },
];

// ------------------------ Финансовая сводка проекта ---------------------- //

export interface SummaryComponent {
  label: string;
  amount: string;
  source: string;
}

export interface ProjectSummary {
  project: string;
  currency: string;
  approvedBudget: string;
  committed: string;
  actual: string;
  remaining: string;
  forecast: string;
  deviation: string;
  deviationTone: Tone;
  committedBreakdown: SummaryComponent[];
  actualBreakdown: SummaryComponent[];
}

export const projectSummary: ProjectSummary = {
  project: "Реконструкция коллектора · МУП «Водоканал»",
  currency: "RUB",
  approvedBudget: "8 600 000,00",
  committed: "3 100 000,00",
  actual: "4 250 000,00",
  remaining: "4 350 000,00",
  forecast: "7 350 000,00",
  deviation: "−1 250 000,00",
  deviationTone: "emerald",
  committedBreakdown: [
    { label: "Заказы поставщикам", amount: "2 100 000,00", source: "purchase_orders" },
    { label: "Договоры (расходные)", amount: "700 000,00", source: "contracts" },
    { label: "Ручные обязательства", amount: "300 000,00", source: "financial_commitments" },
  ],
  actualBreakdown: [
    { label: "Полученные заказы", amount: "2 950 000,00", source: "purchase_orders" },
    { label: "ФОТ (утверждённый)", amount: "1 300 000,00", source: "payroll_drafts" },
  ],
};

// ------------------------- План-факт по проектам ------------------------- //

export interface PlanFactRow {
  project: string;
  budget: number;
  committed: number;
  actual: number;
  forecast: number;
}

export const planFact: PlanFactRow[] = [
  { project: "Реконструкция коллектора", budget: 8.6, committed: 3.1, actual: 4.25, forecast: 7.35 },
  { project: "Наружные сети НВК", budget: 6.4, committed: 2.2, actual: 1.8, forecast: 4.0 },
  { project: "Коттеджный посёлок «Восход»", budget: 12.4, committed: 5.6, actual: 3.1, forecast: 8.7 },
  { project: "Благоустройство сквера", budget: 1.8, committed: 0.4, actual: 0.9, forecast: 1.3 },
];

// ----------------------------- Бюджет проекта ---------------------------- //

export interface BudgetLineRow {
  code: string;
  category: string;
  description: string;
  planned: string;
  approved: string;
  source: string;
  manual: boolean;
  status: string;
  statusTone: Tone;
}

export const budget = {
  name: "Бюджет проекта · смета СМ-Коллектор-3",
  status: "Утверждён",
  statusTone: "emerald" as Tone,
  version: 1,
  plannedTotal: "8 600 000,00",
  approvedTotal: "8 600 000,00",
};

export const budgetLines: BudgetLineRow[] = [
  { code: "MAT", category: "Материалы", description: "Материалы", planned: "4 200 000,00", approved: "4 200 000,00", source: "Смета", manual: false, status: "Утверждена", statusTone: "emerald" },
  { code: "LAB", category: "Труд (ФОТ)", description: "Труд (ФОТ)", planned: "2 100 000,00", approved: "2 100 000,00", source: "Смета", manual: false, status: "Утверждена", statusTone: "emerald" },
  { code: "MCH", category: "Машины", description: "Машины и механизмы", planned: "1 100 000,00", approved: "1 100 000,00", source: "Смета", manual: false, status: "Утверждена", statusTone: "emerald" },
  { code: "OVH", category: "Накладные", description: "Накладные расходы", planned: "700 000,00", approved: "700 000,00", source: "Смета", manual: false, status: "Утверждена", statusTone: "emerald" },
  { code: "PRF", category: "Прибыль", description: "Сметная прибыль", planned: "500 000,00", approved: "500 000,00", source: "Смета", manual: false, status: "Утверждена", statusTone: "emerald" },
  { code: "—", category: "Прочее", description: "Аренда башенного крана (вне сметы)", planned: "300 000,00", approved: "0,00", source: "Служебная записка №7", manual: true, status: "На согласовании", statusTone: "amber" },
];

// --------------------------- Обязательства ------------------------------- //

export interface CommitmentRow {
  id: string;
  description: string;
  counterparty: string;
  amount: string;
  origin: string;
  originTone: Tone;
  due: string;
  status: string;
  statusTone: Tone;
  risk: RiskLevel;
}

export const commitments: CommitmentRow[] = [
  { id: "ЗК-5041", description: "Труба ПНД Ø315 — 820 м", counterparty: "ТД «ПолимерСнаб»", amount: "2 100 000,00", origin: "Заказ", originTone: "navy", due: "24.07.2026", status: "В работе", statusTone: "amber", risk: "R4" },
  { id: "Д-2201", description: "Субподряд: земляные работы", counterparty: "ООО «ГрунтСтрой»", amount: "700 000,00", origin: "Договор", originTone: "navy", due: "10.08.2026", status: "Активен", statusTone: "emerald", risk: "R3" },
  { id: "ОБ-118", description: "Аренда офиса на объекте", counterparty: "ИП Салихов", amount: "300 000,00", origin: "Ручное", originTone: "gray", due: "01.09.2026", status: "Открыто", statusTone: "amber", risk: "R3" },
];

// -------------------- Счета, заявки на оплату, платежи ------------------- //

export interface InvoiceRow {
  id: string;
  number: string;
  counterparty: string;
  amount: string;
  paid: string;
  due: string;
  status: string;
  statusTone: Tone;
  paymentStatus: string;
  paymentTone: Tone;
}

export const invoices: InvoiceRow[] = [
  { id: "СЧ-4021", number: "№ 214 от 12.07", counterparty: "ТД «ПолимерСнаб»", amount: "2 100 000,00", paid: "2 100 000,00", due: "24.07.2026", status: "Зарегистрирован", statusTone: "navy", paymentStatus: "Оплачен", paymentTone: "emerald" },
  { id: "СЧ-4025", number: "№ 77 от 15.07", counterparty: "ООО «ГрунтСтрой»", amount: "700 000,00", paid: "300 000,00", due: "05.08.2026", status: "Зарегистрирован", statusTone: "navy", paymentStatus: "Частично", paymentTone: "amber" },
  { id: "СЧ-4030", number: "№ 5 от 18.07", counterparty: "ИП Салихов", amount: "300 000,00", paid: "0,00", due: "01.09.2026", status: "Черновик", statusTone: "gray", paymentStatus: "Не оплачен", paymentTone: "red" },
];

export interface PayRequestRow {
  id: string;
  invoice: string;
  counterparty: string;
  amount: string;
  planned: string;
  status: string;
  statusTone: Tone;
  risk: RiskLevel;
}

export const payRequests: PayRequestRow[] = [
  { id: "ЗО-901", invoice: "СЧ-4025", counterparty: "ООО «ГрунтСтрой»", amount: "400 000,00", planned: "30.07.2026", status: "На согласовании", statusTone: "amber", risk: "R3" },
  { id: "ЗО-898", invoice: "СЧ-4021", counterparty: "ТД «ПолимерСнаб»", amount: "2 100 000,00", planned: "22.07.2026", status: "Оплачена", statusTone: "emerald", risk: "R4" },
  { id: "ЗО-895", invoice: "СЧ-4030", counterparty: "ИП Салихов", amount: "300 000,00", planned: "28.08.2026", status: "Согласована", statusTone: "navy", risk: "R3" },
];

export interface PaymentRow {
  id: string;
  invoice: string;
  counterparty: string;
  amount: string;
  date: string;
  method: string;
  status: string;
  statusTone: Tone;
}

export const payments: PaymentRow[] = [
  { id: "ПЛ-5501", invoice: "СЧ-4021", counterparty: "ТД «ПолимерСнаб»", amount: "2 100 000,00", date: "22.07.2026", method: "Ручной ввод", status: "Проведён", statusTone: "emerald" },
  { id: "ПЛ-5504", invoice: "СЧ-4025", counterparty: "ООО «ГрунтСтрой»", amount: "300 000,00", date: "24.07.2026", method: "Ручной ввод", status: "Проведён", statusTone: "emerald" },
];

export const payables = {
  invoiced: "3 100 000,00",
  approved: "700 000,00",
  paid: "2 400 000,00",
  outstanding: "700 000,00",
};
