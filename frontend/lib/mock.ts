/*
 * Демонстрационные (mock) данные интерфейса Badrudin AI OS.
 * ВНИМАНИЕ: все данные вымышленные, для показа интерфейса. Реальных
 * персональных данных, секретов и подключения к production здесь нет.
 * Соответствие канону сущностей — DATABASE.md раздел 2.9, D-009.
 */

import type { IconName } from "./icons";

export type RiskLevel = "R0" | "R1" | "R2" | "R3" | "R4";

export interface KpiItem {
  label: string;
  value: string;
  trend?: string;
  up?: boolean;
  icon: IconName;
  tone: string;
  foot?: string;
}

export const company = {
  name: "ООО «Экстра-Элит»",
  system: "Badrudin AI OS",
  ceo: "Бадрудин М.",
  role: "Генеральный директор",
};

/* --------------------------- Панель директора --------------------------- */

export const ceoKpis: KpiItem[] = [
  { label: "Активные объекты", value: "8", trend: "+2", up: true, icon: "sites", tone: "navy", foot: "за квартал" },
  { label: "Задачи на контроле", value: "146", trend: "+12", up: true, icon: "tasks", tone: "emerald", foot: "за неделю" },
  { label: "Просроченные", value: "9", trend: "+3", up: false, icon: "clock", tone: "red", foot: "требуют решения" },
  { label: "Ждут согласования", value: "5", trend: "R3/R4", up: false, icon: "approvals", tone: "amber", foot: "уровни риска" },
];

export const revenueByMonth = [
  { m: "Фев", v: 42 },
  { m: "Мар", v: 51 },
  { m: "Апр", v: 48 },
  { m: "Май", v: 63 },
  { m: "Июн", v: 71 },
  { m: "Июл", v: 84 },
];

export const ceoPriorities = [
  { title: "Согласовать бюджет объекта «Северный коллектор»", meta: "Финансы · R4 · срок сегодня", risk: "R4" as RiskLevel },
  { title: "Утвердить договор субподряда СМР-142", meta: "Юрист · R3 · срок завтра", risk: "R3" as RiskLevel },
  { title: "Решение по замене материала (аналог трубы ПНД)", meta: "Снабжение · R2 · 2 дня", risk: "R2" as RiskLevel },
  { title: "Назначить ответственного по объекту «Парковая, 12»", meta: "Кадры · R2 · 3 дня", risk: "R2" as RiskLevel },
];

export const ceoRisks = [
  { title: "Отставание от графика — «Северный коллектор»", level: "Высокий", tone: "red" },
  { title: "Риск кассового разрыва в августе", level: "Средний", tone: "amber" },
  { title: "Задержка поставки трубы ПНД на 5 дней", level: "Средний", tone: "amber" },
];

export const dailyDigest = [
  { time: "08:30", text: "Сформирована утренняя сводка: 3 письма на решение, 9 просроченных задач." },
  { time: "10:15", text: "ИИ-агент снабжения предложил 2 аналога материала на согласование." },
  { time: "12:40", text: "Прораб объекта «Парковая, 12» приложил фотоотчёт за смену." },
  { time: "15:05", text: "Контролёр исполнения эскалировал 2 заблокированные задачи." },
];

/* ------------------------------- Объекты -------------------------------- */

export interface Site {
  id: string;
  name: string;
  customer: string;
  address: string;
  manager: string;
  progress: number;
  status: string;
  statusTone: string;
  budgetM: number;
  spentM: number;
  deadline: string;
  risk: RiskLevel;
}

export const sites: Site[] = [
  { id: "OBJ-001", name: "Северный коллектор", customer: "МУП «Водоканал»", address: "г. Грозный, ул. Индустриальная", manager: "Ахмедов Р.", progress: 46, status: "Отставание", statusTone: "amber", budgetM: 128.4, spentM: 71.2, deadline: "30.11.2026", risk: "R3" },
  { id: "OBJ-002", name: "ЖК «Парковая, 12»", customer: "АО «СтройИнвест»", address: "г. Грозный, ул. Парковая, 12", manager: "Дошуков И.", progress: 72, status: "В графике", statusTone: "emerald", budgetM: 214.0, spentM: 141.8, deadline: "15.03.2027", risk: "R2" },
  { id: "OBJ-003", name: "Наружные сети НВК", customer: "Администрация района", address: "с. Гелдаган", manager: "Ахмедов Р.", progress: 88, status: "Завершение", statusTone: "navy", budgetM: 54.7, spentM: 49.1, deadline: "20.08.2026", risk: "R1" },
  { id: "OBJ-004", name: "Реконструкция школы №7", customer: "Управление образования", address: "г. Аргун", manager: "Кадыров А.", progress: 33, status: "В графике", statusTone: "emerald", budgetM: 96.3, spentM: 28.9, deadline: "01.09.2027", risk: "R2" },
  { id: "OBJ-005", name: "Благоустройство сквера", customer: "Мэрия г. Грозный", address: "г. Грозный, пр. Победы", manager: "Дошуков И.", progress: 61, status: "В графике", statusTone: "emerald", budgetM: 37.2, spentM: 22.4, deadline: "10.10.2026", risk: "R1" },
  { id: "OBJ-006", name: "Водозабор «Терек»", customer: "МУП «Водоканал»", address: "Наурский р-н", manager: "Кадыров А.", progress: 18, status: "Старт", statusTone: "gray", budgetM: 183.5, spentM: 21.0, deadline: "30.06.2028", risk: "R3" },
];

export const designWorks = [
  { id: "PRJ-011", name: "ПИР: сети водоснабжения, 2 очередь", stage: "Рабочая документация", gip: "Умаров Т.", progress: 64, deadline: "12.09.2026" },
  { id: "PRJ-012", name: "Генплан жилого квартала", stage: "Согласование", gip: "Умаров Т.", progress: 80, deadline: "25.08.2026" },
  { id: "PRJ-013", name: "Дизайн-проект интерьера офиса", stage: "Концепция", gip: "Джаватова Л.", progress: 40, deadline: "05.10.2026" },
];

/* ------------------------------- Задачи --------------------------------- */

export interface Task {
  id: string;
  title: string;
  site: string;
  assignee: string;
  due: string;
  status: string;
  statusTone: string;
  priority: "Высокий" | "Средний" | "Низкий";
  overdue?: boolean;
}

export const tasks: Task[] = [
  { id: "T-2041", title: "Устранить замечание по акту скрытых работ", site: "Северный коллектор", assignee: "Ахмедов Р.", due: "17.07.2026", status: "Просрочена", statusTone: "red", priority: "Высокий", overdue: true },
  { id: "T-2038", title: "Подготовить заявку на трубу ПНД Ø315", site: "Северный коллектор", assignee: "Снабжение", due: "18.07.2026", status: "Выполняется", statusTone: "navy", priority: "Высокий" },
  { id: "T-2050", title: "Фотоотчёт по монтажу колодцев", site: "Наружные сети НВК", assignee: "Прораб", due: "19.07.2026", status: "Ожидает проверки", statusTone: "amber", priority: "Средний" },
  { id: "T-2033", title: "Проверить исполнительную схему участка 4", site: "ЖК «Парковая, 12»", assignee: "Инженер ПТО", due: "16.07.2026", status: "Просрочена", statusTone: "red", priority: "Высокий", overdue: true },
  { id: "T-2061", title: "Согласовать график бетонирования", site: "Реконструкция школы №7", assignee: "Кадыров А.", due: "21.07.2026", status: "Принята в работу", statusTone: "navy", priority: "Средний" },
  { id: "T-2044", title: "Обновить смету по изменению объёмов", site: "ЖК «Парковая, 12»", assignee: "Сметчик", due: "22.07.2026", status: "Черновик", statusTone: "gray", priority: "Низкий" },
  { id: "T-2029", title: "Закрыть заявку на материалы (щебень)", site: "Благоустройство сквера", assignee: "Снабжение", due: "20.07.2026", status: "Выполнена", statusTone: "emerald", priority: "Средний" },
  { id: "T-2019", title: "Подготовить КС-2 за июнь", site: "Наружные сети НВК", assignee: "Инженер ПТО", due: "15.07.2026", status: "Просрочена", statusTone: "red", priority: "Высокий", overdue: true },
];

export const taskStats = [
  { label: "Всего активных", value: 146 },
  { label: "В работе", value: 92 },
  { label: "Ожидают проверки", value: 27 },
  { label: "Просрочено", value: 9 },
];

/* ----------------------------- Согласования ----------------------------- */

export interface Approval {
  id: string;
  subject: string;
  type: string;
  amount?: string;
  initiator: string;
  risk: RiskLevel;
  status: "Ожидает" | "Согласовано" | "Отклонено";
  statusTone: string;
  date: string;
}

export const approvals: Approval[] = [
  { id: "APR-501", subject: "Бюджет объекта «Северный коллектор»", type: "Финансы", amount: "128,4 млн ₽", initiator: "ИИ-финансовый агент", risk: "R4", status: "Ожидает", statusTone: "amber", date: "19.07.2026" },
  { id: "APR-502", subject: "Договор субподряда СМР-142", type: "Юридический документ", amount: "12,7 млн ₽", initiator: "ИИ-агент юриста", risk: "R3", status: "Ожидает", statusTone: "amber", date: "19.07.2026" },
  { id: "APR-503", subject: "Замена материала: аналог трубы ПНД", type: "Снабжение", amount: "1,9 млн ₽", initiator: "ИИ-агент снабжения", risk: "R2", status: "Ожидает", statusTone: "amber", date: "18.07.2026" },
  { id: "APR-498", subject: "Выдача подотчётных средств прорабу", type: "Финансы", amount: "150 000 ₽", initiator: "Дошуков И.", risk: "R2", status: "Согласовано", statusTone: "emerald", date: "17.07.2026" },
  { id: "APR-495", subject: "Назначение ответственного по объекту", type: "Кадры", initiator: "Исполнительный директор", risk: "R2", status: "Согласовано", statusTone: "emerald", date: "16.07.2026" },
  { id: "APR-490", subject: "Публикация в соцсетях (проект сквера)", type: "Маркетинг", initiator: "ИИ-SMM-агент", risk: "R1", status: "Отклонено", statusTone: "red", date: "15.07.2026" },
];

export const riskScale: { level: RiskLevel; title: string; desc: string }[] = [
  { level: "R0", title: "Без риска", desc: "Чтение и справочные действия — без согласования." },
  { level: "R1", title: "Низкий", desc: "Обычные операции, обратимые изменения." },
  { level: "R2", title: "Средний", desc: "Значимые изменения, согласование руководителя направления." },
  { level: "R3", title: "Высокий", desc: "Финансово/юридически значимо — согласование уполномоченного лица." },
  { level: "R4", title: "Критический", desc: "Только после подтверждения человека и усиленной аутентификации." },
];

/* ------------------------------- Финансы -------------------------------- */

export const financeKpis: KpiItem[] = [
  { label: "Бюджет проектов", value: "714 млн ₽", trend: "+4%", up: true, icon: "finance", tone: "navy", foot: "суммарно" },
  { label: "Освоено", value: "334 млн ₽", trend: "47%", up: true, icon: "reports", tone: "emerald", foot: "от бюджета" },
  { label: "Кассовый прогноз", value: "−6,2 млн ₽", trend: "август", up: false, icon: "alert", tone: "red", foot: "риск разрыва" },
  { label: "Подотчётные", value: "1,74 млн ₽", trend: "12 лиц", up: true, icon: "employees", tone: "amber", foot: "на контроле" },
];

export const budgetsBySite = [
  { site: "Северный коллектор", budget: 128.4, spent: 71.2 },
  { site: "ЖК «Парковая, 12»", budget: 214.0, spent: 141.8 },
  { site: "Наружные сети НВК", budget: 54.7, spent: 49.1 },
  { site: "Реконструкция школы №7", budget: 96.3, spent: 28.9 },
  { site: "Водозабор «Терек»", budget: 183.5, spent: 21.0 },
];

export const cashflow = [
  { m: "Май", income: 58, expense: 44 },
  { m: "Июн", income: 63, expense: 61 },
  { m: "Июл", income: 71, expense: 66 },
  { m: "Авг", income: 49, expense: 55 },
  { m: "Сен", income: 74, expense: 60 },
];

export const advances = [
  { person: "Дошуков И.", site: "ЖК «Парковая, 12»", issued: "150 000 ₽", spent: "112 400 ₽", balance: "37 600 ₽", due: "25.07.2026", tone: "emerald" },
  { person: "Ахмедов Р.", site: "Северный коллектор", issued: "200 000 ₽", spent: "205 800 ₽", balance: "−5 800 ₽", due: "20.07.2026", tone: "red" },
  { person: "Кадыров А.", site: "Реконструкция школы №7", issued: "80 000 ₽", spent: "31 000 ₽", balance: "49 000 ₽", due: "31.07.2026", tone: "emerald" },
];

/* ------------------------------ Снабжение ------------------------------- */

export interface Purchase {
  id: string;
  material: string;
  qty: string;
  site: string;
  supplier: string;
  sum: string;
  status: string;
  statusTone: string;
  eta: string;
}

export const purchases: Purchase[] = [
  { id: "PO-3012", material: "Труба ПНД Ø315 SDR17", qty: "820 м", site: "Северный коллектор", supplier: "ТД «ПолимерСнаб»", sum: "3,2 млн ₽", status: "Задержка", statusTone: "red", eta: "24.07.2026" },
  { id: "PO-3015", material: "Щебень фр. 20–40", qty: "140 т", site: "Благоустройство сквера", supplier: "Карьер «Терский»", sum: "0,49 млн ₽", status: "В пути", statusTone: "navy", eta: "20.07.2026" },
  { id: "PO-3009", material: "Бетон B25 W6", qty: "60 м³", site: "Реконструкция школы №7", supplier: "«БетонГрупп»", sum: "0,38 млн ₽", status: "Поставлено", statusTone: "emerald", eta: "16.07.2026" },
  { id: "PO-3021", material: "Колодцы ж/б КЦ-15", qty: "24 шт", site: "Наружные сети НВК", supplier: "«ЖБИ-Юг»", sum: "0,72 млн ₽", status: "Согласование", statusTone: "amber", eta: "27.07.2026" },
  { id: "PO-3024", material: "Арматура А500С Ø12", qty: "18 т", site: "ЖК «Парковая, 12»", supplier: "«МеталлТорг»", sum: "1,15 млн ₽", status: "Заявка", statusTone: "gray", eta: "01.08.2026" },
];

export const procurementKpis: KpiItem[] = [
  { label: "Открытые заявки", value: "23", trend: "+5", up: true, icon: "procurement", tone: "navy", foot: "по 6 объектам" },
  { label: "В пути", value: "7", trend: "поставки", up: true, icon: "sites", tone: "emerald", foot: "на этой неделе" },
  { label: "Задержки", value: "2", trend: "риск сроков", up: false, icon: "clock", tone: "red", foot: "требуют решения" },
  { label: "Экономия закупок", value: "3,4%", trend: "к плану", up: true, icon: "reports", tone: "amber", foot: "за квартал" },
];

export const suppliers = [
  { name: "ТД «ПолимерСнаб»", category: "Трубы, полимеры", rating: 4.2, orders: 34, onTime: "88%" },
  { name: "«БетонГрупп»", category: "Бетон, растворы", rating: 4.7, orders: 51, onTime: "96%" },
  { name: "«МеталлТорг»", category: "Металлопрокат", rating: 4.4, orders: 28, onTime: "91%" },
  { name: "Карьер «Терский»", category: "Инертные материалы", rating: 4.0, orders: 19, onTime: "84%" },
];

/* ------------------------------ Документы ------------------------------- */

export interface Doc {
  id: string;
  name: string;
  type: string;
  site: string;
  author: string;
  version: string;
  date: string;
  access: string;
  accessTone: string;
}

export const documents: Doc[] = [
  { id: "DOC-7781", name: "Договор субподряда СМР-142.pdf", type: "Договор", site: "Северный коллектор", author: "Юрист", version: "v3", date: "18.07.2026", access: "Ограничен", accessTone: "amber" },
  { id: "DOC-7770", name: "КС-2 июнь — Наружные сети.xlsx", type: "Акт КС-2", site: "Наружные сети НВК", author: "Инженер ПТО", version: "v1", date: "15.07.2026", access: "Внутренний", accessTone: "navy" },
  { id: "DOC-7765", name: "Исполнительная схема уч.4.pdf", type: "Исполнительная документация", site: "ЖК «Парковая, 12»", author: "Инженер ПТО", version: "v2", date: "14.07.2026", access: "Внутренний", accessTone: "navy" },
  { id: "DOC-7752", name: "Локальная смета №12.gsfx", type: "Смета", site: "Реконструкция школы №7", author: "Сметчик", version: "v4", date: "12.07.2026", access: "Ограничен", accessTone: "amber" },
  { id: "DOC-7740", name: "Фотоотчёт смена 14.07.zip", type: "Фотоотчёт", site: "ЖК «Парковая, 12»", author: "Прораб", version: "v1", date: "14.07.2026", access: "Внутренний", accessTone: "navy" },
  { id: "DOC-7728", name: "Проектная документация 2 очередь.pdf", type: "Проект", site: "ПИР сети НВК", author: "ГИП", version: "v5", date: "10.07.2026", access: "Публичный", accessTone: "emerald" },
];

export const docCategories = [
  { name: "Договоры", count: 42, icon: "documents" },
  { name: "Исполнительная документация", count: 168, icon: "approvals" },
  { name: "Сметы", count: 57, icon: "finance" },
  { name: "Фото и видео", count: 934, icon: "sites" },
];

/* ------------------------------ Сотрудники ------------------------------ */

export interface Employee {
  name: string;
  position: string;
  dept: string;
  status: "Активен" | "В отпуске" | "На объекте";
  statusTone: string;
  projects: number;
  initials: string;
}

export const employees: Employee[] = [
  { name: "Бадрудин М.", position: "Генеральный директор", dept: "Руководство", status: "Активен", statusTone: "emerald", projects: 6, initials: "БМ" },
  { name: "Мадаев С.", position: "Исполнительный директор", dept: "Руководство", status: "Активен", statusTone: "emerald", projects: 6, initials: "МС" },
  { name: "Ахмедов Р.", position: "Производственный директор", dept: "Производство", status: "На объекте", statusTone: "navy", projects: 3, initials: "АР" },
  { name: "Умаров Т.", position: "Главный инженер проекта", dept: "Проектный отдел", status: "Активен", statusTone: "emerald", projects: 2, initials: "УТ" },
  { name: "Дошуков И.", position: "Прораб", dept: "Производство", status: "На объекте", statusTone: "navy", projects: 2, initials: "ДИ" },
  { name: "Кадыров А.", position: "Прораб", dept: "Производство", status: "Активен", statusTone: "emerald", projects: 2, initials: "КА" },
  { name: "Джаватова Л.", position: "Дизайнер интерьеров", dept: "Архитектура и дизайн", status: "В отпуске", statusTone: "amber", projects: 1, initials: "ДЛ" },
  { name: "Исраилова М.", position: "Инженер ПТО", dept: "Производство", status: "Активен", statusTone: "emerald", projects: 4, initials: "ИМ" },
];

export const orgStructure = [
  { dept: "Руководство", head: "Бадрудин М.", people: 2 },
  { dept: "Производство", head: "Ахмедов Р.", people: 14 },
  { dept: "Проектный отдел", head: "Умаров Т.", people: 9 },
  { dept: "Архитектура и дизайн", head: "Джаватова Л.", people: 4 },
  { dept: "Снабжение", head: "Тагиров Б.", people: 3 },
  { dept: "Финансы и бухгалтерия", head: "Эльдарова З.", people: 3 },
];

/* ------------------------------ ИИ-агенты ------------------------------- */

export interface Agent {
  name: string;
  role: string;
  status: "Активен" | "Ожидание" | "Пауза";
  statusTone: string;
  mode: string;
  runs: number;
  lastRun: string;
}

export const agents: Agent[] = [
  { name: "ИИ-помощник директора", role: "Сводки и приоритеты", status: "Активен", statusTone: "emerald", mode: "Подготовка на согласование", runs: 128, lastRun: "10 мин назад" },
  { name: "Контролёр исполнения", role: "Контроль поручений", status: "Активен", statusTone: "emerald", mode: "Разрешённая автоматизация", runs: 342, lastRun: "3 мин назад" },
  { name: "ИИ-агент снабжения", role: "Заявки и поставщики", status: "Активен", statusTone: "emerald", mode: "Только рекомендация", runs: 87, lastRun: "22 мин назад" },
  { name: "ИИ-финансовый агент", role: "Платёжный календарь", status: "Ожидание", statusTone: "amber", mode: "Подготовка на согласование", runs: 64, lastRun: "1 ч назад" },
  { name: "ИИ-агент юриста", role: "Проекты договоров", status: "Активен", statusTone: "emerald", mode: "Отправка после утверждения", runs: 41, lastRun: "40 мин назад" },
  { name: "Независимый ИИ-аудитор", role: "Проверка результатов агентов", status: "Активен", statusTone: "emerald", mode: "Экстренная эскалация", runs: 96, lastRun: "15 мин назад" },
  { name: "ИИ-SMM-агент", role: "Контент и публикации", status: "Пауза", statusTone: "gray", mode: "Отправка после утверждения", runs: 22, lastRun: "2 дня назад" },
];

export const agentModes = [
  "Только рекомендация",
  "Подготовка на согласование",
  "Отправка после утверждения",
  "Разрешённая автоматизация",
  "Экстренная эскалация",
];

/* ------------------------------- Отчёты --------------------------------- */

export const reportKpis: KpiItem[] = [
  { label: "Задачи в срок", value: "83%", trend: "+5 п.п.", up: true, icon: "tasks", tone: "emerald", foot: "за месяц" },
  { label: "Отклонение бюджета", value: "+2,8%", trend: "к плану", up: false, icon: "finance", tone: "amber", foot: "по портфелю" },
  { label: "Закрыто ИД", value: "76%", trend: "+3 п.п.", up: true, icon: "documents", tone: "navy", foot: "исп. документация" },
  { label: "Открытые риски", value: "14", trend: "3 критич.", up: false, icon: "alert", tone: "red", foot: "на контроле" },
];

export interface Risk {
  title: string;
  category: string;
  site: string;
  level: "Критический" | "Высокий" | "Средний" | "Низкий";
  levelTone: string;
  owner: string;
  measure: string;
}

export const risks: Risk[] = [
  { title: "Отставание от графика на 12 дней", category: "Сроки", site: "Северный коллектор", level: "Критический", levelTone: "red", owner: "Ахмедов Р.", measure: "Корректирующий график, доп. бригада" },
  { title: "Риск кассового разрыва в августе", category: "Финансы", site: "Портфель", level: "Высокий", levelTone: "amber", owner: "Эльдарова З.", measure: "Пересмотр платёжного календаря" },
  { title: "Задержка поставки трубы ПНД", category: "Снабжение", site: "Северный коллектор", level: "Высокий", levelTone: "amber", owner: "Тагиров Б.", measure: "Поиск альтернативного поставщика" },
  { title: "Неполнота исполнительной документации", category: "ПТО", site: "Наружные сети НВК", level: "Средний", levelTone: "amber", owner: "Исраилова М.", measure: "План закрытия актов до сдачи" },
  { title: "Замечания заказчика по разделу ВК", category: "Проект", site: "ПИР сети НВК", level: "Низкий", levelTone: "emerald", owner: "Умаров Т.", measure: "Реестр замечаний, срок ответа" },
];

export const reportsList = [
  { name: "Ежедневная сводка директора", period: "19.07.2026", type: "Управленческий" },
  { name: "Отчёт по объектам за неделю", period: "13–19.07.2026", type: "Производственный" },
  { name: "План-факт по бюджету", period: "Июль 2026", type: "Финансовый" },
  { name: "Отчёт по закупкам", period: "II квартал 2026", type: "Снабжение" },
];

/* ------------------------------ Настройки ------------------------------- */

export const settingsSections = [
  { key: "profile", title: "Профиль и организация" },
  { key: "security", title: "Безопасность и доступ" },
  { key: "notifications", title: "Уведомления" },
  { key: "agents", title: "ИИ-агенты и режимы" },
  { key: "integrations", title: "Интеграции" },
];

export const integrations = [
  { name: "Электронная почта (SMTP)", desc: "Официальная рассылка поручений", on: true },
  { name: "Telegram (бот-канал)", desc: "Оперативные уведомления", on: true },
  { name: "n8n — оркестрация процессов", desc: "Автоматизация сценариев", on: true },
  { name: "MinIO — файловое хранилище", desc: "Документы, фото и видео", on: true },
  { name: "Экспорт в бухгалтерию", desc: "Ручная выгрузка (адаптер)", on: false },
  { name: "Meta Business Suite", desc: "Публикация контента", on: false },
];
