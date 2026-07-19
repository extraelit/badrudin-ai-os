/*
 * Демонстрационные (mock) данные модуля «Сметы и ценообразование».
 * Все данные вымышленные, только для показа интерфейса. Реальных ПДн, секретов
 * и подключения к production нет.
 *
 * Переиспользование канона (DATABASE.md разделы 6, 9, 11, 12, 16, 18):
 *   проекты/объекты/зоны → projects/sites/project_locations;
 *   материалы и цены → materials/supplier_products; труд → payroll;
 *   документы сметы → documents/document_versions; согласования → approvals;
 *   факт объёмов → daily_report_work_items; аудит → audit_events.
 */
import type { IconName } from "./icons";

export interface EstKpi {
  label: string;
  value: string;
  trend?: string;
  up?: boolean;
  icon: IconName;
  tone: string;
  foot?: string;
}

export const estimateProject = { name: "ЖК «Парковая, 12»", role: "Сметный отдел" };

export const estimateKpis: EstKpi[] = [
  { label: "Сметы по проекту", value: "6", trend: "3 утверждены", up: true, icon: "finance", tone: "navy", foot: "локальные/объектные" },
  { label: "Утверждённая стоимость", value: "214,6 млн ₽", trend: "R2", up: true, icon: "reports", tone: "emerald", foot: "grand total" },
  { label: "Отклонение план-факт", value: "+2,8%", trend: "прогноз", up: false, icon: "alert", tone: "amber", foot: "по объёмам" },
  { label: "КП на согласовании", value: "2", trend: "R3/R4", up: false, icon: "approvals", tone: "amber", foot: "ждут решения" },
];

export type Tone = "emerald" | "amber" | "red" | "gray" | "navy";

export interface EstimateRow {
  id: string;
  name: string;
  type: string;
  version: number;
  status: string;
  statusTone: Tone;
  grand: string;
  deviation: string;
  deviationTone: Tone;
}

export const estimates: EstimateRow[] = [
  { id: "СМ-101", name: "Локальная смета: земляные работы", type: "Локальная", version: 3, status: "Утверждена", statusTone: "emerald", grand: "18,4 млн ₽", deviation: "+1,2%", deviationTone: "amber" },
  { id: "СМ-102", name: "Локальная смета: сети ВК", type: "Локальная", version: 2, status: "Утверждена", statusTone: "emerald", grand: "42,1 млн ₽", deviation: "0%", deviationTone: "emerald" },
  { id: "СМ-103", name: "Локальная смета: отделка МОП", type: "Локальная", version: 1, status: "На проверке", statusTone: "amber", grand: "9,8 млн ₽", deviation: "—", deviationTone: "gray" },
  { id: "ОС-201", name: "Объектная смета: корпус 1", type: "Объектная", version: 2, status: "Утверждена", statusTone: "emerald", grand: "154,1 млн ₽", deviation: "+3,4%", deviationTone: "red" },
  { id: "СВ-301", name: "Сводный сметный расчёт", type: "Сводная", version: 1, status: "Черновик", statusTone: "gray", grand: "214,6 млн ₽", deviation: "—", deviationTone: "gray" },
];

export interface PositionRow {
  no: number;
  code: string;
  name: string;
  unit: string;
  qty: string;
  material: string;
  labor: string;
  machine: string;
  overhead: string;
  profit: string;
  total: string;
}

export const positions: PositionRow[] = [
  { no: 1, code: "ГЭСН 01-01-003", name: "Разработка грунта экскаватором", unit: "м³", qty: "1 200", material: "12 000 ₽", labor: "84 000 ₽", machine: "156 000 ₽", overhead: "15%", profit: "8%", total: "312 480 ₽" },
  { no: 2, code: "ГЭСН 22-03-002", name: "Укладка трубопровода ПНД Ø315", unit: "м", qty: "820", material: "2 624 000 ₽", labor: "246 000 ₽", machine: "98 000 ₽", overhead: "15%", profit: "8%", total: "3 683 800 ₽" },
  { no: 3, code: "СН-15-01", name: "Монтаж колодцев ж/б КЦ-15", unit: "шт", qty: "24", material: "720 000 ₽", labor: "144 000 ₽", machine: "72 000 ₽", overhead: "15%", profit: "8%", total: "1 106 900 ₽" },
  { no: 4, code: "СН-31-04", name: "Обратная засыпка с уплотнением", unit: "м³", qty: "980", material: "0 ₽", labor: "117 600 ₽", machine: "88 200 ₽", overhead: "15%", profit: "8%", total: "255 700 ₽" },
];

export const estimateTotals = [
  { label: "Материалы", value: "3 356 000 ₽" },
  { label: "Труд (ФОТ)", value: "591 600 ₽" },
  { label: "Машины и механизмы", value: "414 200 ₽" },
  { label: "Прямые затраты", value: "4 361 800 ₽" },
  { label: "Накладные расходы (15%)", value: "654 270 ₽" },
  { label: "Сметная прибыль (8%)", value: "401 286 ₽" },
  { label: "Итого без НДС", value: "5 417 356 ₽" },
  { label: "НДС (20%)", value: "1 083 471 ₽" },
];
export const estimateGrand = "6 500 827 ₽";

export interface VolumeRow {
  work: string;
  unit: string;
  planned: string;
  actual: string;
  foreman: string;
  date: string;
  verification: string;
  vTone: Tone;
}

export const workVolumes: VolumeRow[] = [
  { work: "Разработка грунта экскаватором", unit: "м³", planned: "1 200", actual: "1 080", foreman: "Ахмедов Р.", date: "18.07.2026", verification: "Проверено", vTone: "emerald" },
  { work: "Укладка трубопровода ПНД", unit: "м", planned: "820", actual: "642", foreman: "Дошуков И.", date: "18.07.2026", verification: "Проверено", vTone: "emerald" },
  { work: "Монтаж колодцев", unit: "шт", planned: "24", actual: "18", foreman: "Дошуков И.", date: "17.07.2026", verification: "На проверке", vTone: "amber" },
  { work: "Обратная засыпка", unit: "м³", planned: "980", actual: "610", foreman: "Ахмедов Р.", date: "17.07.2026", verification: "Отклонено", vTone: "red" },
];

export interface RateRow {
  code: string;
  name: string;
  unit: string;
  material: string;
  labor: string;
  machine: string;
  source: string;
  sourceTone: Tone;
}

export const rateItems: RateRow[] = [
  { code: "ГЭСН 01-01-003", name: "Разработка грунта экскаватором", unit: "м³", material: "10 ₽", labor: "70 ₽", machine: "130 ₽", source: "ГЭСН", sourceTone: "navy" },
  { code: "ГЭСН 22-03-002", name: "Укладка трубопровода ПНД Ø315", unit: "м", material: "3 200 ₽", labor: "300 ₽", machine: "120 ₽", source: "ГЭСН", sourceTone: "navy" },
  { code: "СН-15-01", name: "Монтаж колодцев ж/б КЦ-15", unit: "шт", material: "30 000 ₽", labor: "6 000 ₽", machine: "3 000 ₽", source: "Собственная", sourceTone: "emerald" },
  { code: "СН-31-04", name: "Обратная засыпка с уплотнением", unit: "м³", material: "0 ₽", labor: "120 ₽", machine: "90 ₽", source: "Собственная", sourceTone: "emerald" },
];

export interface OfferRow {
  id: string;
  estimate: string;
  base: string;
  markup: string;
  offer: string;
  status: string;
  statusTone: Tone;
  risk: "R3" | "R4";
}

export const offers: OfferRow[] = [
  { id: "КП-501", estimate: "ОС-201 корпус 1", base: "154,1 млн ₽", markup: "12%", offer: "172,6 млн ₽", status: "На согласовании", statusTone: "amber", risk: "R4" },
  { id: "КП-498", estimate: "СМ-102 сети ВК", base: "42,1 млн ₽", markup: "10%", offer: "46,3 млн ₽", status: "Согласовано", statusTone: "emerald", risk: "R3" },
  { id: "КП-495", estimate: "СМ-101 земляные", base: "18,4 млн ₽", markup: "8%", offer: "19,9 млн ₽", status: "Черновик", statusTone: "gray", risk: "R3" },
];

export interface PlanFactRow {
  position: string;
  plannedQty: string;
  actualQty: string;
  plannedTotal: string;
  actualTotal: string;
  deviation: string;
  devTone: Tone;
}

export const planFact: PlanFactRow[] = [
  { position: "Разработка грунта", plannedQty: "1 200 м³", actualQty: "1 080 м³", plannedTotal: "312 480 ₽", actualTotal: "281 232 ₽", deviation: "−31 248 ₽", devTone: "emerald" },
  { position: "Укладка трубопровода", plannedQty: "820 м", actualQty: "642 м", plannedTotal: "3 683 800 ₽", actualTotal: "2 884 000 ₽", deviation: "−799 800 ₽", devTone: "emerald" },
  { position: "Монтаж колодцев", plannedQty: "24 шт", actualQty: "18 шт", plannedTotal: "1 106 900 ₽", actualTotal: "830 175 ₽", deviation: "−276 725 ₽", devTone: "emerald" },
  { position: "Обратная засыпка", plannedQty: "980 м³", actualQty: "610 м³", plannedTotal: "255 700 ₽", actualTotal: "159 200 ₽", deviation: "−96 500 ₽", devTone: "emerald" },
];

export const planFactTotals = { planned: "5 358 880 ₽", actual: "4 154 607 ₽", forecast: "6 690 000 ₽", deviation: "+2,8%" };

export interface ChangeRow {
  id: string;
  type: string;
  reason: string;
  delta: string;
  deltaTone: Tone;
  date: string;
  author: string;
  status: string;
  statusTone: Tone;
}

export const changes: ChangeRow[] = [
  { id: "ИЗ-071", type: "Объём", reason: "Уточнение объёмов земляных работ по факту", delta: "−31 248 ₽", deltaTone: "emerald", date: "18.07.2026", author: "Сметчик", status: "Утверждено", statusTone: "emerald" },
  { id: "ИЗ-069", type: "Цена", reason: "Рост цены трубы ПНД по согласованному КП поставщика", delta: "+184 000 ₽", deltaTone: "red", date: "16.07.2026", author: "Агент цен", status: "На согласовании", statusTone: "amber" },
  { id: "ИЗ-065", type: "Новая версия", reason: "Изменение проектного решения по разделу ВК", delta: "—", deltaTone: "gray", date: "12.07.2026", author: "Сметчик", status: "Версия 2", statusTone: "navy" },
];
