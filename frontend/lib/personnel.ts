/*
 * Демонстрационные (mock) данные модуля «Персонал объектов / Производственный учёт».
 * Все данные вымышленные, только для показа интерфейса. Реальных ПДн, секретов
 * и подключения к production нет.
 *
 * Переиспользование канона (без дублирования, DATABASE.md раздел 2.9, D-009):
 *   работники      → employees;  объекты → sites/projects;  бригады → project_members;
 *   инструктажи/допуски/удостоверения → documents (document_type: instruction/permit/certificate);
 *   начисления, авансы, удержания → финансовый контур (advances/accounting_exports);
 *   выплаты и подтверждения → approvals (R0–R4);  все действия → audit_events.
 * Новые прикладные сущности (появятся в модели данных на этапе бэкенда):
 *   site_shifts (табель), payroll_drafts (начисления), safety_clearances (ОТ),
 *   foreman_journals (журналы), daily_report_headcount (отчёт прораба).
 */
import type { RiskLevel } from "./mock";

/* --------- Виджеты панели директора (сводно по всем объектам) --------- */

export const personnelWidgets = [
  { label: "Людей на объектах сегодня", value: "184", trend: "из 212 план", up: true, icon: "employees", tone: "navy", foot: "явка 87%" },
  { label: "ФОТ за текущий месяц", value: "6,84 млн ₽", trend: "предв.", up: true, icon: "finance", tone: "emerald", foot: "черновик" },
  { label: "Без действующего допуска", value: "7", trend: "работников", up: false, icon: "alert", tone: "red", foot: "не допускать" },
  { label: "Инструктаж не подписан", value: "12", trend: "подписей", up: false, icon: "documents", tone: "amber", foot: "требует действий" },
  { label: "Журналы не заполнены", value: "5", trend: "журналов", up: false, icon: "reports", tone: "amber", foot: "по 3 объектам" },
  { label: "Объекты с нехваткой людей", value: "3", trend: "объекта", up: false, icon: "sites", tone: "red", foot: "ниже плана" },
] as const;

/* ------------------- 1. Сводка директора по объектам ------------------- */

export interface SitePersonnelRow {
  site: string;
  planned: number;
  actual: number;
  onSite: number;
  absent: number;
  hoursDay: number;
  overtime: number;
  idle: number;
  fotMonthM: number;
  noPermit: number;
  unsignedBriefings: number;
  unfilledJournals: number;
  violations: number;
  tone: string;
}

export const sitePersonnel: SitePersonnelRow[] = [
  { site: "Северный коллектор", planned: 48, actual: 39, onSite: 35, absent: 4, hoursDay: 312, overtime: 18, idle: 6, fotMonthM: 1.94, noPermit: 3, unsignedBriefings: 5, unfilledJournals: 2, violations: 2, tone: "red" },
  { site: "ЖК «Парковая, 12»", planned: 62, actual: 60, onSite: 57, absent: 3, hoursDay: 486, overtime: 22, idle: 2, fotMonthM: 2.61, noPermit: 1, unsignedBriefings: 3, unfilledJournals: 1, violations: 0, tone: "emerald" },
  { site: "Наружные сети НВК", planned: 24, actual: 24, onSite: 22, absent: 2, hoursDay: 184, overtime: 6, idle: 0, fotMonthM: 0.88, noPermit: 0, unsignedBriefings: 1, unfilledJournals: 0, violations: 0, tone: "emerald" },
  { site: "Реконструкция школы №7", planned: 36, actual: 31, onSite: 30, absent: 1, hoursDay: 248, overtime: 9, idle: 4, fotMonthM: 1.02, noPermit: 2, unsignedBriefings: 2, unfilledJournals: 1, violations: 1, tone: "amber" },
  { site: "Благоустройство сквера", planned: 22, actual: 20, onSite: 20, absent: 0, hoursDay: 160, overtime: 4, idle: 0, fotMonthM: 0.39, noPermit: 0, unsignedBriefings: 1, unfilledJournals: 0, violations: 0, tone: "emerald" },
  { site: "Водозабор «Терек»", planned: 20, actual: 14, onSite: 20, absent: 0, hoursDay: 96, overtime: 0, idle: 8, fotMonthM: 0.0, noPermit: 1, unsignedBriefings: 0, unfilledJournals: 1, violations: 0, tone: "red" },
];

export const directorSummary = {
  planned: 212,
  actual: 188,
  onSite: 184,
  absent: 10,
  hoursDay: 1486,
  hoursMonth: 28940,
  overtime: 59,
  idle: 20,
  fotMonthM: 6.84,
  noPermit: 7,
  unsignedBriefings: 12,
  unfilledJournals: 5,
  violations: 3,
};

/* --------------------- 2. Карточка объекта (люди) ---------------------- */

export interface SiteWorker {
  name: string;
  brigade: string;
  profession: string;
  work: string;
  arrival: string;
  departure: string;
  shift: string;
  hours: number;
  volume: string;
  clearance: "Допущен" | "Не допущен" | "Проверка";
  clearanceTone: string;
  docs: "В порядке" | "Просрочка" | "Не подписан";
  docsTone: string;
  initials: string;
}

export const siteCard = {
  site: "Северный коллектор",
  foreman: "Ахмедов Р.",
  responsible: "Дошуков И. (мастер), Исраилова М. (ПТО)",
  brigades: 3,
  onSite: 35,
  planned: 48,
};

export const siteWorkers: SiteWorker[] = [
  { name: "Магомедов А.", brigade: "Бригада №1", profession: "Монтажник", work: "Монтаж трубопровода уч. 3", arrival: "08:02", departure: "17:05", shift: "Дневная", hours: 8, volume: "42 м", clearance: "Допущен", clearanceTone: "emerald", docs: "В порядке", docsTone: "emerald", initials: "МА" },
  { name: "Идрисов Х.", brigade: "Бригада №1", profession: "Сварщик", work: "Сварка стыков", arrival: "08:00", departure: "17:00", shift: "Дневная", hours: 8, volume: "18 стыков", clearance: "Не допущен", clearanceTone: "red", docs: "Просрочка", docsTone: "red", initials: "ИХ" },
  { name: "Сулейманов Р.", brigade: "Бригада №2", profession: "Экскаваторщик", work: "Разработка траншеи", arrival: "07:50", departure: "16:40", shift: "Дневная", hours: 8, volume: "120 м³", clearance: "Допущен", clearanceTone: "emerald", docs: "В порядке", docsTone: "emerald", initials: "СР" },
  { name: "Абдулаев М.", brigade: "Бригада №2", profession: "Разнорабочий", work: "Обратная засыпка", arrival: "08:10", departure: "17:00", shift: "Дневная", hours: 8, volume: "—", clearance: "Проверка", clearanceTone: "amber", docs: "Не подписан", docsTone: "amber", initials: "АМ" },
  { name: "Юсупов Д.", brigade: "Бригада №3", profession: "Бетонщик", work: "Устройство основания", arrival: "08:05", departure: "17:10", shift: "Дневная", hours: 8, volume: "24 м²", clearance: "Допущен", clearanceTone: "emerald", docs: "В порядке", docsTone: "emerald", initials: "ЮД" },
];

/* ----------------------- 3. Табель рабочего времени -------------------- */

export interface TimesheetRow {
  worker: string;
  brigade: string;
  site: string;
  day: string;
  shift: string;
  hours: number;
  overtime: number;
  idle: number;
  absence: string;
  tone: string;
}

export const timesheet: TimesheetRow[] = [
  { worker: "Магомедов А.", brigade: "Бригада №1", site: "Северный коллектор", day: "18.07.2026", shift: "Дневная", hours: 8, overtime: 2, idle: 0, absence: "—", tone: "emerald" },
  { worker: "Идрисов Х.", brigade: "Бригада №1", site: "Северный коллектор", day: "18.07.2026", shift: "Дневная", hours: 0, overtime: 0, idle: 0, absence: "Недопуск", tone: "red" },
  { worker: "Сулейманов Р.", brigade: "Бригада №2", site: "Северный коллектор", day: "18.07.2026", shift: "Дневная", hours: 8, overtime: 1, idle: 0, absence: "—", tone: "emerald" },
  { worker: "Абдулаев М.", brigade: "Бригада №2", site: "Северный коллектор", day: "18.07.2026", shift: "Дневная", hours: 6, overtime: 0, idle: 2, absence: "—", tone: "amber" },
  { worker: "Юсупов Д.", brigade: "Бригада №3", site: "Северный коллектор", day: "18.07.2026", shift: "Дневная", hours: 8, overtime: 0, idle: 0, absence: "—", tone: "emerald" },
  { worker: "Курбанов Т.", brigade: "Бригада №1", site: "ЖК «Парковая, 12»", day: "18.07.2026", shift: "Ночная", hours: 8, overtime: 0, idle: 0, absence: "—", tone: "emerald" },
  { worker: "Алиев Б.", brigade: "Бригада №2", site: "ЖК «Парковая, 12»", day: "18.07.2026", shift: "Дневная", hours: 0, overtime: 0, idle: 0, absence: "Отпуск", tone: "gray" },
];

export const timesheetTotals = {
  worker: "Магомедов А.",
  period: "01.07–18.07.2026",
  daysWorked: 15,
  hours: 122,
  overtime: 11,
  idle: 3,
  absences: 1,
};

/* -------------------- 4. Предварительный расчёт ФОТ -------------------- */

export interface PayrollRow {
  worker: string;
  profession: string;
  scheme: "Почасовая" | "Посменная" | "Окладная" | "Сдельная";
  rate: string;
  qty: string;
  accrued: string;
  advance: string;
  deduction: string;
  toPay: string;
  status: "Черновик" | "Проверено прорабом" | "Согласовано" | "Передано в бухгалтерию";
  statusTone: string;
  risk: RiskLevel;
}

export const payroll: PayrollRow[] = [
  { worker: "Магомедов А.", profession: "Монтажник", scheme: "Почасовая", rate: "420 ₽/ч", qty: "122 ч", accrued: "51 240 ₽", advance: "15 000 ₽", deduction: "0 ₽", toPay: "36 240 ₽", status: "Проверено прорабом", statusTone: "navy", risk: "R2" },
  { worker: "Идрисов Х.", profession: "Сварщик", scheme: "Сдельная", rate: "1 100 ₽/стык", qty: "84 стыка", accrued: "92 400 ₽", advance: "20 000 ₽", deduction: "2 000 ₽", toPay: "70 400 ₽", status: "Черновик", statusTone: "gray", risk: "R3" },
  { worker: "Сулейманов Р.", profession: "Экскаваторщик", scheme: "Посменная", rate: "3 800 ₽/смена", qty: "15 смен", accrued: "57 000 ₽", advance: "18 000 ₽", deduction: "0 ₽", toPay: "39 000 ₽", status: "Согласовано", statusTone: "emerald", risk: "R3" },
  { worker: "Юсупов Д.", profession: "Бетонщик", scheme: "Почасовая", rate: "390 ₽/ч", qty: "118 ч", accrued: "46 020 ₽", advance: "12 000 ₽", deduction: "0 ₽", toPay: "34 020 ₽", status: "Передано в бухгалтерию", statusTone: "emerald", risk: "R2" },
  { worker: "Исраилова М.", profession: "Инженер ПТО", scheme: "Окладная", rate: "95 000 ₽/мес", qty: "1,0 ст.", accrued: "95 000 ₽", advance: "40 000 ₽", deduction: "0 ₽", toPay: "55 000 ₽", status: "Согласовано", statusTone: "emerald", risk: "R3" },
];

export const payrollTotals = {
  accrued: "341 660 ₽",
  advance: "105 000 ₽",
  deduction: "2 000 ₽",
  toPay: "234 660 ₽",
};

export const payrollStages = [
  "Черновик",
  "Проверено прорабом",
  "Согласовано руководителем",
  "Передано в бухгалтерию",
];

/* ---------------------- 5. Охрана труда и допуски ---------------------- */

export interface SafetyRow {
  worker: string;
  profession: string;
  intro: boolean;
  primary: boolean;
  daily: boolean;
  medical: string;
  medicalTone: string;
  certs: string;
  permits: string;
  permitTone: string;
  status: "Допущен" | "Не допущен";
  statusTone: string;
}

export const safety: SafetyRow[] = [
  { worker: "Магомедов А.", profession: "Монтажник", intro: true, primary: true, daily: true, medical: "до 12.2026", medicalTone: "emerald", certs: "Стропальщик", permits: "Высотные — до 09.2026", permitTone: "emerald", status: "Допущен", statusTone: "emerald" },
  { worker: "Идрисов Х.", profession: "Сварщик", intro: true, primary: true, daily: false, medical: "просрочен", medicalTone: "red", certs: "НАКС", permits: "Сварочные — просрочен", permitTone: "red", status: "Не допущен", statusTone: "red" },
  { worker: "Сулейманов Р.", profession: "Экскаваторщик", intro: true, primary: true, daily: true, medical: "до 03.2027", medicalTone: "emerald", certs: "Удостоверение машиниста", permits: "Земляные — действует", permitTone: "emerald", status: "Допущен", statusTone: "emerald" },
  { worker: "Абдулаев М.", profession: "Разнорабочий", intro: true, primary: false, daily: false, medical: "до 05.2027", medicalTone: "emerald", certs: "—", permits: "—", permitTone: "gray", status: "Не допущен", statusTone: "red" },
  { worker: "Юсупов Д.", profession: "Бетонщик", intro: true, primary: true, daily: true, medical: "до 08.2026", medicalTone: "amber", certs: "—", permits: "—", permitTone: "gray", status: "Допущен", statusTone: "emerald" },
];

export const safetyBriefings = [
  { name: "Вводный инструктаж", desc: "При приёме на работу", icon: "documents" },
  { name: "Первичный на рабочем месте", desc: "Перед началом работ на объекте", icon: "sites" },
  { name: "Ежедневный / целевой", desc: "Перед сменой и спецработами", icon: "clock" },
];

/* -------------------------- 6. Журналы прораба ------------------------- */

export interface JournalRow {
  name: string;
  site: string;
  responsible: string;
  status: "Заполнен" | "Не заполнен" | "Просрочен" | "Требует проверки";
  statusTone: string;
  due: string;
  attachments: number;
}

export const journals: JournalRow[] = [
  { name: "Общий журнал работ", site: "Северный коллектор", responsible: "Ахмедов Р.", status: "Требует проверки", statusTone: "amber", due: "19.07.2026", attachments: 4 },
  { name: "Журнал входного контроля", site: "Северный коллектор", responsible: "Исраилова М.", status: "Не заполнен", statusTone: "red", due: "18.07.2026", attachments: 0 },
  { name: "Журнал инструктажей", site: "Северный коллектор", responsible: "Дошуков И.", status: "Заполнен", statusTone: "emerald", due: "18.07.2026", attachments: 6 },
  { name: "Журнал производства работ", site: "ЖК «Парковая, 12»", responsible: "Кадыров А.", status: "Заполнен", statusTone: "emerald", due: "18.07.2026", attachments: 3 },
  { name: "Журнал сварочных работ", site: "Северный коллектор", responsible: "Идрисов Х.", status: "Просрочен", statusTone: "red", due: "16.07.2026", attachments: 1 },
  { name: "Журнал бетонных работ", site: "Реконструкция школы №7", responsible: "Кадыров А.", status: "Требует проверки", statusTone: "amber", due: "19.07.2026", attachments: 2 },
  { name: "Журнал земляных работ", site: "Северный коллектор", responsible: "Сулейманов Р.", status: "Заполнен", statusTone: "emerald", due: "18.07.2026", attachments: 2 },
];

/* --------------------- 7. Карточка работника --------------------------- */

export const worker = {
  name: "Магомедов Ахмед",
  profession: "Монтажник наружных трубопроводов",
  brigade: "Бригада №1",
  initials: "МА",
  status: "На объекте",
  statusTone: "navy",
  phone: "скрыт (демо)",
  hiredAt: "12.03.2025",
};

export const workerSites = [
  { site: "Северный коллектор", period: "с 01.06.2026", role: "Монтажник", current: true },
  { site: "Наружные сети НВК", period: "02.2026 – 05.2026", role: "Монтажник", current: false },
];

export const workerBriefings = [
  { name: "Вводный инструктаж", date: "12.03.2025", signed: true },
  { name: "Первичный на рабочем месте", date: "01.06.2026", signed: true },
  { name: "Целевой (высотные работы)", date: "15.07.2026", signed: true },
];

export const workerPermits = [
  { name: "Медосмотр", until: "12.2026", tone: "emerald" },
  { name: "Удостоверение стропальщика", until: "04.2027", tone: "emerald" },
  { name: "Допуск: высотные работы", until: "09.2026", tone: "amber" },
];

export const workerViolations = [
  { date: "20.06.2026", text: "Отсутствие каски на объекте", severity: "Замечание", tone: "amber" },
];

export const workerPayroll = [
  { month: "Июнь 2026", accrued: "48 900 ₽", paid: "48 900 ₽", status: "Выплачено", tone: "emerald" },
  { month: "Июль 2026", accrued: "51 240 ₽", paid: "— (черновик)", status: "Проверено прорабом", tone: "navy" },
];

/* --------------------- 8. Ежедневный отчёт прораба --------------------- */

export const dailyReport = {
  site: "Северный коллектор",
  date: "18.07.2026",
  foreman: "Ахмедов Р.",
  status: "Ожидает подтверждения",
  statusTone: "amber",
};

export const dailyByProfession = [
  { profession: "Монтажники", count: 8 },
  { profession: "Сварщики", count: 3 },
  { profession: "Экскаваторщики", count: 2 },
  { profession: "Бетонщики", count: 5 },
  { profession: "Разнорабочие", count: 12 },
];

export const dailyWorks = [
  { work: "Монтаж трубопровода, уч. 3", unit: "м", plan: 50, fact: 42 },
  { work: "Разработка траншеи", unit: "м³", plan: 130, fact: 120 },
  { work: "Устройство основания", unit: "м²", plan: 30, fact: 24 },
];

export const dailyEquipment = [
  { name: "Экскаватор Hyundai R220", hours: 8, tone: "emerald" },
  { name: "Самосвал КамАЗ (2 ед.)", hours: 7, tone: "emerald" },
  { name: "Сварочный аппарат", hours: 0, tone: "red" },
];

export const dailyIssues = [
  { type: "Простой", text: "Сварочные работы приостановлены — недопуск сварщика (просрочен медосмотр)", tone: "red" },
  { type: "Материалы", text: "Получена труба ПНД Ø315 — 40 м из 60 м", tone: "amber" },
];
