/*
 * Демонстрационные (mock) данные модуля «Снабжение и закупки».
 * Все данные вымышленные, только для показа интерфейса. Реальных ПДн, секретов
 * и подключения к production нет.
 *
 * Переиспользование канона (DATABASE.md разделы 11, 12, 14, 33):
 *   материалы → materials (≡ inventory_items §33); ед. изм. → units_of_measure;
 *   поставщики и цены → suppliers/supplier_products; сравнение КП →
 *   quote_comparisons; согласования → approvals (R2/R3/R4); документы/сертификаты
 *   → documents/document_versions/files; связь со сметой → estimate_positions;
 *   аудит → audit_events.
 */
import type { IconName } from "./icons";

export interface ProcKpi {
  label: string;
  value: string;
  trend?: string;
  up?: boolean;
  icon: IconName;
  tone: string;
  foot?: string;
}

export const procKpis: ProcKpi[] = [
  { label: "Открытые заявки", value: "23", trend: "+5", up: true, icon: "procurement", tone: "navy", foot: "по 6 объектам" },
  { label: "Заказы в работе", value: "9", trend: "7 в пути", up: true, icon: "sites", tone: "emerald", foot: "ожидают поставки" },
  { label: "Ждут согласования", value: "3", trend: "R3/R4", up: false, icon: "approvals", tone: "amber", foot: "заказы/списания" },
  { label: "Позиции на складе", value: "412", trend: "2 склада", up: true, icon: "documents", tone: "navy", foot: "остатки" },
];

export type Tone = "emerald" | "amber" | "red" | "gray" | "navy";

export interface RequestRow {
  id: string;
  site: string;
  material: string;
  qty: string;
  needed: string;
  status: string;
  statusTone: Tone;
  inEstimate: boolean;
}

export const requests: RequestRow[] = [
  { id: "З-3012", site: "Северный коллектор", material: "Труба ПНД Ø315 SDR17", qty: "820 м", needed: "24.07.2026", status: "Утверждена", statusTone: "emerald", inEstimate: true },
  { id: "З-3015", site: "Благоустройство сквера", material: "Щебень фр. 20–40", qty: "140 т", needed: "20.07.2026", status: "На согласовании", statusTone: "amber", inEstimate: true },
  { id: "З-3021", site: "Наружные сети НВК", material: "Колодцы ж/б КЦ-15", qty: "24 шт", needed: "27.07.2026", status: "Черновик", statusTone: "gray", inEstimate: true },
  { id: "З-3024", site: "ЖК «Парковая, 12»", material: "Арматура А500С Ø12", qty: "18 т", needed: "01.08.2026", status: "Утверждена", statusTone: "emerald", inEstimate: false },
];

export interface RfqRow {
  id: string;
  material: string;
  suppliers: number;
  offers: number;
  best: string;
  bestSupplier: string;
  status: string;
  statusTone: Tone;
}

export const rfqs: RfqRow[] = [
  { id: "ЗЦ-711", material: "Труба ПНД Ø315", suppliers: 4, offers: 4, best: "3 100 ₽/м", bestSupplier: "ТД «ПолимерСнаб»", status: "Сравнено", statusTone: "emerald" },
  { id: "ЗЦ-712", material: "Щебень фр. 20–40", suppliers: 3, offers: 2, best: "3 400 ₽/т", bestSupplier: "Карьер «Терский»", status: "Сбор предложений", statusTone: "amber" },
  { id: "ЗЦ-708", material: "Арматура А500С", suppliers: 2, offers: 2, best: "62 000 ₽/т", bestSupplier: "«МеталлТорг»", status: "Сравнено", statusTone: "emerald" },
];

export interface RfqOffer {
  supplier: string;
  price: string;
  lead: string;
  best: boolean;
}

export const rfqOffers: RfqOffer[] = [
  { supplier: "ТД «ПолимерСнаб»", price: "3 100 ₽/м", lead: "7 дн", best: true },
  { supplier: "«ТрубаТорг»", price: "3 260 ₽/м", lead: "10 дн", best: false },
  { supplier: "«ЮгПолимер»", price: "3 340 ₽/м", lead: "5 дн", best: false },
  { supplier: "«СнабКомплект»", price: "3 480 ₽/м", lead: "14 дн", best: false },
];

export interface OrderRow {
  id: string;
  supplier: string;
  material: string;
  amount: string;
  eta: string;
  status: string;
  statusTone: Tone;
  risk: "R3" | "R4";
}

export const orders: OrderRow[] = [
  { id: "ЗК-5041", supplier: "ТД «ПолимерСнаб»", material: "Труба ПНД Ø315 — 820 м", amount: "2,54 млн ₽", eta: "24.07.2026", status: "На согласовании", statusTone: "amber", risk: "R4" },
  { id: "ЗК-5038", supplier: "«БетонГрупп»", material: "Бетон B25 — 60 м³", amount: "0,38 млн ₽", eta: "16.07.2026", status: "Поставлен", statusTone: "emerald", risk: "R3" },
  { id: "ЗК-5033", supplier: "Карьер «Терский»", material: "Щебень — 140 т", amount: "0,49 млн ₽", eta: "20.07.2026", status: "В пути", statusTone: "navy", risk: "R3" },
  { id: "ЗК-5029", supplier: "«МеталлТорг»", material: "Арматура — 18 т", amount: "1,15 млн ₽", eta: "01.08.2026", status: "Черновик", statusTone: "gray", risk: "R4" },
];

export interface ReceiptRow {
  id: string;
  order: string;
  supplier: string;
  received: string;
  accepted: string;
  rejected: string;
  quality: string;
  qualityTone: Tone;
  cert: string;
  certTone: Tone;
}

export const receipts: ReceiptRow[] = [
  { id: "П-8801", order: "ЗК-5038", supplier: "«БетонГрупп»", received: "60 м³", accepted: "60 м³", rejected: "0", quality: "Годно", qualityTone: "emerald", cert: "Есть", certTone: "emerald" },
  { id: "П-8804", order: "ЗК-5033", supplier: "Карьер «Терский»", received: "140 т", accepted: "134 т", rejected: "6 т", quality: "Частично", qualityTone: "amber", cert: "Есть", certTone: "emerald" },
  { id: "П-8807", order: "—", supplier: "«ЖБИ-Юг»", received: "24 шт", accepted: "22 шт", rejected: "2 шт", quality: "Брак", qualityTone: "red", cert: "Нет", certTone: "red" },
];

export interface BalanceRow {
  material: string;
  warehouse: string;
  qty: string;
  reserved: string;
  avgCost: string;
}

export const balances: BalanceRow[] = [
  { material: "Труба ПНД Ø315 SDR17", warehouse: "Центральный склад", qty: "620 м", reserved: "180 м", avgCost: "3 120 ₽/м" },
  { material: "Щебень фр. 20–40", warehouse: "Склад объекта", qty: "134 т", reserved: "0", avgCost: "3 380 ₽/т" },
  { material: "Арматура А500С Ø12", warehouse: "Центральный склад", qty: "18 т", reserved: "18 т", avgCost: "61 500 ₽/т" },
  { material: "Бетон B25 W6", warehouse: "Склад объекта", qty: "0 м³", reserved: "0", avgCost: "6 300 ₽/м³" },
];

export interface MovementRow {
  id: string;
  type: string;
  typeTone: Tone;
  material: string;
  qty: string;
  warehouse: string;
  date: string;
  status: string;
  statusTone: Tone;
}

export const movements: MovementRow[] = [
  { id: "ДВ-9012", type: "Поступление", typeTone: "emerald", material: "Щебень фр. 20–40", qty: "+134 т", warehouse: "Склад объекта", date: "18.07.2026", status: "Проведено", statusTone: "emerald" },
  { id: "ДВ-9015", type: "Выдача", typeTone: "navy", material: "Труба ПНД Ø315", qty: "−200 м", warehouse: "Центральный склад", date: "18.07.2026", status: "Проведено", statusTone: "emerald" },
  { id: "ДВ-9018", type: "Перемещение", typeTone: "navy", material: "Арматура А500С", qty: "18 т", warehouse: "Центр → Объект", date: "17.07.2026", status: "Проведено", statusTone: "emerald" },
  { id: "ДВ-9021", type: "Списание", typeTone: "red", material: "Колодцы ж/б (брак)", qty: "−2 шт", warehouse: "Склад объекта", date: "17.07.2026", status: "На согласовании", statusTone: "amber" },
];

export interface IssueRow {
  id: string;
  site: string;
  material: string;
  qty: string;
  issuedTo: string;
  date: string;
  status: string;
  statusTone: Tone;
}

export const issues: IssueRow[] = [
  { id: "В-4401", site: "Северный коллектор", material: "Труба ПНД Ø315", qty: "200 м", issuedTo: "Ахмедов Р.", date: "18.07.2026", status: "Проведено", statusTone: "emerald" },
  { id: "В-4404", site: "Благоустройство сквера", material: "Щебень фр. 20–40", qty: "40 т", issuedTo: "Дошуков И.", date: "18.07.2026", status: "Проведено", statusTone: "emerald" },
  { id: "В-4407", site: "ЖК «Парковая, 12»", material: "Арматура А500С", qty: "6 т", issuedTo: "Кадыров А.", date: "17.07.2026", status: "Черновик", statusTone: "gray" },
];

export interface CountRow {
  material: string;
  expected: string;
  counted: string;
  diff: string;
  diffTone: Tone;
}

export const inventoryCount = {
  number: "ИНВ-2026-07",
  warehouse: "Центральный склад",
  date: "18.07.2026",
  status: "Проведена",
};

export const countLines: CountRow[] = [
  { material: "Труба ПНД Ø315", expected: "640 м", counted: "620 м", diff: "−20 м", diffTone: "amber" },
  { material: "Арматура А500С Ø12", expected: "18 т", counted: "18 т", diff: "0", diffTone: "emerald" },
  { material: "Колодцы ж/б КЦ-15", expected: "24 шт", counted: "22 шт", diff: "−2 шт", diffTone: "red" },
];
