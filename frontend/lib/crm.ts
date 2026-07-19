/*
 * Демонстрационные (mock) данные модуля «Ядро CRM».
 * Все данные вымышленные, только для показа интерфейса. Реальных ПДн, секретов
 * и подключения к production нет; телефоны и e-mail показаны в маскированном
 * виде (как для пользователя без права crm.contact.pii).
 *
 * Переиспользование канона (DATABASE.md разделы 10.4, 11, 16):
 *   заказчики → counterparties; контакты → counterparty_contacts; коммерческие
 *   предложения → commercial_offers (сметный модуль); задачи → tasks; проекты и
 *   договоры-объекты → projects/contracts; согласования → approvals (R2/R3/R4);
 *   коммуникации → communications; аудит → audit_events.
 */
import type { IconName } from "./icons";

export type Tone = "emerald" | "amber" | "red" | "gray" | "navy";
export type RiskLevel = "R0" | "R1" | "R2" | "R3" | "R4";

export interface CrmKpi {
  label: string;
  value: string;
  trend?: string;
  up?: boolean;
  icon: IconName;
  tone: string;
  foot?: string;
}

export const crmKpis: CrmKpi[] = [
  { label: "Сделки в работе", value: "18", trend: "+4", up: true, icon: "finance", tone: "navy", foot: "открытые" },
  { label: "Сумма воронки", value: "64,2 млн ₽", trend: "взвеш. 41,8 млн", up: true, icon: "reports", tone: "emerald", foot: "по всем этапам" },
  { label: "Конверсия", value: "38 %", trend: "выигрыш/закрытые", up: true, icon: "approvals", tone: "amber", foot: "за квартал" },
  { label: "Новые лиды", value: "12", trend: "7 не обработаны", up: false, icon: "employees", tone: "navy", foot: "за неделю" },
];

// -------------------------------- Воронка -------------------------------- //

export interface FunnelStage {
  name: string;
  count: number;
  amount: string;
  probability: number;
  won?: boolean;
  lost?: boolean;
}

export const funnel: FunnelStage[] = [
  { name: "Новый лид", count: 12, amount: "8,4 млн ₽", probability: 10 },
  { name: "Квалифицирован", count: 9, amount: "14,2 млн ₽", probability: 25 },
  { name: "Коммерческое предложение", count: 6, amount: "19,6 млн ₽", probability: 50 },
  { name: "Переговоры", count: 4, amount: "12,8 млн ₽", probability: 70 },
  { name: "Договор", count: 3, amount: "9,2 млн ₽", probability: 90 },
  { name: "Выиграна", count: 7, amount: "22,5 млн ₽", probability: 100, won: true },
  { name: "Проиграна", count: 5, amount: "6,1 млн ₽", probability: 0, lost: true },
];

// --------------------------------- Лиды ---------------------------------- //

export interface LeadRow {
  id: string;
  title: string;
  company: string;
  source: string;
  contact: string;
  phone: string;
  amount: string;
  status: string;
  statusTone: Tone;
  responsible: string;
}

export const leads: LeadRow[] = [
  { id: "Л-1042", title: "Наружные сети для ЖК", company: "ООО «СтройИнвест»", source: "Сайт", contact: "А. Магомедов", phone: "***4567", amount: "3,2 млн ₽", status: "Новый", statusTone: "navy", responsible: "И. Даниялов" },
  { id: "Л-1039", title: "Благоустройство территории", company: "ТСЖ «Каспий»", source: "Рекомендация", contact: "М. Алиева", phone: "***1290", amount: "1,8 млн ₽", status: "Квалифицирован", statusTone: "emerald", responsible: "И. Даниялов" },
  { id: "Л-1035", title: "Проект коттеджного посёлка", company: "ИП Гаджиев", source: "Выставка", contact: "Р. Гаджиев", phone: "***7781", amount: "5,6 млн ₽", status: "Новый", statusTone: "navy", responsible: "С. Курбанова" },
  { id: "Л-1028", title: "Ремонт офиса", company: "ООО «ТоргДом»", source: "Звонок", contact: "Н. Идрисов", phone: "***3345", amount: "0,9 млн ₽", status: "Отклонён", statusTone: "red", responsible: "С. Курбанова" },
];

// -------------------------------- Сделки --------------------------------- //

export interface DealRow {
  id: string;
  title: string;
  client: string;
  amount: string;
  stage: string;
  status: string;
  statusTone: Tone;
  risk: RiskLevel;
  responsible: string;
  close: string;
}

export const deals: DealRow[] = [
  { id: "С-5012", title: "Наружные сети НВК", client: "ООО «СтройИнвест»", amount: "3,2 млн ₽", stage: "Переговоры", status: "Открыта", statusTone: "navy", risk: "R3", responsible: "И. Даниялов", close: "10.08.2026" },
  { id: "С-5008", title: "Благоустройство сквера", client: "ТСЖ «Каспий»", amount: "1,8 млн ₽", stage: "Коммерческое предложение", status: "Открыта", statusTone: "navy", risk: "R3", responsible: "И. Даниялов", close: "22.08.2026" },
  { id: "С-4998", title: "Коттеджный посёлок «Восход»", client: "ИП Гаджиев", amount: "12,4 млн ₽", stage: "Договор", status: "Открыта", statusTone: "amber", risk: "R4", responsible: "С. Курбанова", close: "05.09.2026" },
  { id: "С-4990", title: "Реконструкция коллектора", client: "МУП «Водоканал»", amount: "8,6 млн ₽", stage: "Выиграна", status: "Выиграна", statusTone: "emerald", risk: "R3", responsible: "С. Курбанова", close: "01.07.2026" },
  { id: "С-4982", title: "Ремонт кровли склада", client: "ООО «ТоргДом»", amount: "0,9 млн ₽", stage: "Проиграна", status: "Проиграна", statusTone: "red", risk: "R2", responsible: "И. Даниялов", close: "18.06.2026" },
];

// доска сделок по этапам (канбан)
export interface KanbanCard {
  id: string;
  title: string;
  client: string;
  amount: string;
  risk: RiskLevel;
}
export interface KanbanColumn {
  stage: string;
  probability: number;
  cards: KanbanCard[];
}

export const kanban: KanbanColumn[] = [
  { stage: "Квалифицирован", probability: 25, cards: [
    { id: "С-5015", title: "Ливневая канализация", client: "ООО «Гранд»", amount: "2,1 млн ₽", risk: "R3" },
  ] },
  { stage: "Коммерческое предложение", probability: 50, cards: [
    { id: "С-5008", title: "Благоустройство сквера", client: "ТСЖ «Каспий»", amount: "1,8 млн ₽", risk: "R3" },
  ] },
  { stage: "Переговоры", probability: 70, cards: [
    { id: "С-5012", title: "Наружные сети НВК", client: "ООО «СтройИнвест»", amount: "3,2 млн ₽", risk: "R3" },
  ] },
  { stage: "Договор", probability: 90, cards: [
    { id: "С-4998", title: "Коттеджный посёлок «Восход»", client: "ИП Гаджиев", amount: "12,4 млн ₽", risk: "R4" },
  ] },
];

// ------------------------------ Заказчики -------------------------------- //

export interface CounterpartyRow {
  id: string;
  name: string;
  inn: string;
  type: string;
  deals: number;
  amount: string;
  status: string;
  statusTone: Tone;
}

export const counterparties: CounterpartyRow[] = [
  { id: "К-301", name: "ООО «СтройИнвест»", inn: "0561xxxxxx", type: "Заказчик", deals: 3, amount: "6,4 млн ₽", status: "Активен", statusTone: "emerald" },
  { id: "К-298", name: "ТСЖ «Каспий»", inn: "0554xxxxxx", type: "Заказчик", deals: 2, amount: "2,7 млн ₽", status: "Активен", statusTone: "emerald" },
  { id: "К-295", name: "ИП Гаджиев Р. М.", inn: "0572xxxxxx", type: "Заказчик", deals: 1, amount: "12,4 млн ₽", status: "Активен", statusTone: "emerald" },
  { id: "К-290", name: "МУП «Водоканал»", inn: "0541xxxxxx", type: "Заказчик", deals: 4, amount: "18,2 млн ₽", status: "Активен", statusTone: "emerald" },
];

export interface ContactRow {
  name: string;
  position: string;
  email: string;
  phone: string;
  consent: boolean;
  primary: boolean;
}

export const contacts: ContactRow[] = [
  { name: "Ахмед Магомедов", position: "Директор", email: "a***@stroyinvest.ru", phone: "***4567", consent: true, primary: true },
  { name: "Марьям Алиева", position: "Главный инженер", email: "m***@stroyinvest.ru", phone: "***2210", consent: true, primary: false },
  { name: "Саид Османов", position: "Бухгалтер", email: "s***@stroyinvest.ru", phone: "***9987", consent: false, primary: false },
];

// ---------------------------- Коммуникации ------------------------------- //

export interface CommRow {
  id: string;
  channel: string;
  channelTone: Tone;
  direction: string;
  subject: string;
  counterparty: string;
  when: string;
  status: string;
  statusTone: Tone;
}

export const communications: CommRow[] = [
  { id: "КМ-812", channel: "E-mail", channelTone: "navy", direction: "Входящее", subject: "Запрос коммерческого предложения", counterparty: "ООО «СтройИнвест»", when: "18.07 14:20", status: "Задача создана", statusTone: "emerald" },
  { id: "КМ-809", channel: "WhatsApp", channelTone: "emerald", direction: "Входящее", subject: "Уточнение по срокам", counterparty: "ТСЖ «Каспий»", when: "18.07 11:05", status: "Новое", statusTone: "amber" },
  { id: "КМ-806", channel: "Звонок", channelTone: "navy", direction: "Исходящее", subject: "Согласование встречи", counterparty: "ИП Гаджиев", when: "17.07 16:40", status: "Обработано", statusTone: "gray" },
  { id: "КМ-801", channel: "Веб-форма", channelTone: "amber", direction: "Входящее", subject: "Заявка с сайта", counterparty: "ООО «Гранд»", when: "17.07 09:15", status: "Новое", statusTone: "amber" },
];

// ------------------------------ Договоры --------------------------------- //

export interface ContractRow {
  id: string;
  number: string;
  client: string;
  subject: string;
  amount: string;
  status: string;
  statusTone: Tone;
  risk: RiskLevel;
  signed: string;
}

export const contracts: ContractRow[] = [
  { id: "Д-2201", number: "12/2026", client: "МУП «Водоканал»", subject: "Реконструкция коллектора", amount: "8,6 млн ₽", status: "Подписан", statusTone: "emerald", risk: "R3", signed: "01.07.2026" },
  { id: "Д-2205", number: "15/2026", client: "ИП Гаджиев", subject: "Коттеджный посёлок «Восход»", amount: "12,4 млн ₽", status: "На согласовании", statusTone: "amber", risk: "R4", signed: "—" },
  { id: "Д-2208", number: "16/2026", client: "ООО «СтройИнвест»", subject: "Наружные сети НВК", amount: "3,2 млн ₽", status: "Черновик", statusTone: "gray", risk: "R3", signed: "—" },
];

// ------------------------ Коммерческие предложения ----------------------- //

export interface OfferRow {
  id: string;
  deal: string;
  client: string;
  estimate: string;
  markup: string;
  offer: string;
  status: string;
  statusTone: Tone;
  risk: RiskLevel;
}

export const offers: OfferRow[] = [
  { id: "КП-711", deal: "С-4998", client: "ИП Гаджиев", estimate: "СМ-Восход-1", markup: "12 %", offer: "12,4 млн ₽", status: "На согласовании", statusTone: "amber", risk: "R4" },
  { id: "КП-708", deal: "С-5008", client: "ТСЖ «Каспий»", estimate: "СМ-Сквер-2", markup: "10 %", offer: "1,8 млн ₽", status: "Отправлено", statusTone: "navy", risk: "R3" },
  { id: "КП-702", deal: "С-4990", client: "МУП «Водоканал»", estimate: "СМ-Коллектор-3", markup: "9 %", offer: "8,6 млн ₽", status: "Утверждено", statusTone: "emerald", risk: "R3" },
];

// ------------------------- Аналитика: менеджеры -------------------------- //

export interface ManagerRow {
  name: string;
  deals: number;
  won: number;
  wonAmount: string;
  target: string;
  planFact: number;
}

export const managers: ManagerRow[] = [
  { name: "И. Даниялов", deals: 9, won: 4, wonAmount: "11,8 млн ₽", target: "15,0 млн ₽", planFact: 79 },
  { name: "С. Курбанова", deals: 7, won: 3, wonAmount: "10,7 млн ₽", target: "12,0 млн ₽", planFact: 89 },
];

// ----------------------------- Причины потерь ---------------------------- //

export interface LossRow {
  reason: string;
  count: number;
  amount: string;
}

export const lossReasons: LossRow[] = [
  { reason: "Дорого", count: 3, amount: "3,6 млн ₽" },
  { reason: "Выбрали конкурента", count: 1, amount: "1,6 млн ₽" },
  { reason: "Отложен проект", count: 1, amount: "0,9 млн ₽" },
];
