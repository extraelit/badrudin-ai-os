/*
 * Демонстрационные (mock) данные модуля «Проектирование и дизайн».
 * Все данные вымышленные, только для показа интерфейса. Реальных ПДн, секретов
 * и подключения к production нет.
 *
 * Переиспользование канона (DATABASE.md разделы 6, 10, 11, 12, 18):
 *   проекты/объекты → projects/sites; зоны → project_locations;
 *   чертежи и ТЗ → documents/document_versions/files; задания разделам → tasks;
 *   согласования выпуска → approvals (R2/R3/R4); поставщики/материалы → suppliers.
 */
import type { IconName } from "./icons";

export interface DesignKpi {
  label: string;
  value: string;
  trend?: string;
  up?: boolean;
  icon: IconName;
  tone: string;
  foot?: string;
}

export const designProject = { name: "ЖК «Парковая, 12» — интерьеры и сети", gip: "Умаров Т." };

export const designKpis: DesignKpi[] = [
  { label: "Разделы проекта", value: "9", trend: "2 выпущены", up: true, icon: "tasks", tone: "navy", foot: "по проекту" },
  { label: "Средняя готовность", value: "63%", trend: "+6%", up: true, icon: "reports", tone: "emerald", foot: "за неделю" },
  { label: "Открытые замечания", value: "11", trend: "3 критич.", up: false, icon: "alert", tone: "amber", foot: "→ задачи" },
  { label: "Ждут проверки ГИП", value: "4", trend: "раздела", up: false, icon: "approvals", tone: "amber", foot: "комплектность" },
];

export type GipTone = "emerald" | "amber" | "red" | "gray" | "navy";

export interface Discipline {
  code: string;
  name: string;
  type: string;
  responsible: string;
  due: string;
  completion: number;
  gip: string;
  gipTone: GipTone;
  status: string;
  statusTone: GipTone;
}

export const disciplines: Discipline[] = [
  { code: "АР", name: "Архитектурные решения", type: "architecture", responsible: "Джаватова Л.", due: "12.09.2026", completion: 82, gip: "Проверено", gipTone: "emerald", status: "В работе", statusTone: "navy" },
  { code: "КР", name: "Конструктивные решения", type: "structural", responsible: "Умаров Т.", due: "20.09.2026", completion: 70, gip: "На проверке", gipTone: "amber", status: "В работе", statusTone: "navy" },
  { code: "ВК", name: "Водоснабжение и водоотведение", type: "water_supply", responsible: "Исраилова М.", due: "05.09.2026", completion: 95, gip: "Проверено", gipTone: "emerald", status: "Выпущен", statusTone: "emerald" },
  { code: "ЭОМ", name: "Электроснабжение", type: "electrical", responsible: "Кадыров А.", due: "18.09.2026", completion: 55, gip: "Ожидает", gipTone: "gray", status: "В работе", statusTone: "navy" },
  { code: "ОВ", name: "Отопление и вентиляция", type: "hvac", responsible: "Кадыров А.", due: "25.09.2026", completion: 40, gip: "Ожидает", gipTone: "gray", status: "В работе", statusTone: "navy" },
  { code: "ГП", name: "Генеральный план", type: "general_plan", responsible: "Умаров Т.", due: "01.09.2026", completion: 100, gip: "Проверено", gipTone: "emerald", status: "Выпущен", statusTone: "emerald" },
  { code: "ИД", name: "Дизайн интерьеров", type: "interior", responsible: "Джаватова Л.", due: "10.10.2026", completion: 48, gip: "Отклонено", gipTone: "red", status: "На доработке", statusTone: "red" },
];

export const brief = {
  title: "Техническое задание — интерьеры и наружные сети",
  client: "АО «СтройИнвест»",
  functional: "Жилой квартал: 2 корпуса, паркинг, благоустройство; интерьеры МОП и лобби.",
  style: "Современный минимализм, тёплая нейтральная палитра, натуральные материалы.",
  budget: "180–214 млн ₽",
  target: "15.03.2027",
  status: "Утверждено",
  statusTone: "emerald" as GipTone,
};

export interface Concept {
  name: string;
  version: number;
  author: string;
  status: string;
  statusTone: GipTone;
  feedback: string;
}

export const concepts: Concept[] = [
  { name: "Лобби и входная группа", version: 3, author: "Джаватова Л.", status: "Утверждена", statusTone: "emerald", feedback: "Заказчик согласовал финальный вариант." },
  { name: "Места общего пользования", version: 2, author: "Джаватова Л.", status: "На проверке клиента", statusTone: "amber", feedback: "Ожидаются замечания по освещению." },
  { name: "Благоустройство двора", version: 1, author: "Умаров Т.", status: "Черновик", statusTone: "gray", feedback: "—" },
];

export interface Specification {
  category: string;
  name: string;
  material: string;
  supplier: string;
  qty: string;
  price: string;
  analog: boolean;
  status: string;
  statusTone: GipTone;
}

export const specifications: Specification[] = [
  { category: "Отделка", name: "Керамогранит лобби 600×600", material: "Керамогранит", supplier: "ТД «Отделка+»", qty: "180 м²", price: "2 400 ₽/м²", analog: true, status: "Утверждено", statusTone: "emerald" },
  { category: "Освещение", name: "Трековые светильники LED", material: "Светильник LED 30Вт", supplier: "«СветоТорг»", qty: "64 шт", price: "3 900 ₽", analog: true, status: "Проверено", statusTone: "navy" },
  { category: "Мебель", name: "Диван для лобби", material: "Мягкая мебель", supplier: "«Интерьер-М»", qty: "4 шт", price: "84 000 ₽", analog: false, status: "Черновик", statusTone: "gray" },
  { category: "Оборудование", name: "Насос повысительный", material: "Насос Ø50", supplier: "«ПолимерСнаб»", qty: "2 шт", price: "128 000 ₽", analog: true, status: "Проверено", statusTone: "navy" },
];

export interface DesignIssueRow {
  id: string;
  title: string;
  source: string;
  severity: string;
  severityTone: GipTone;
  status: string;
  statusTone: GipTone;
  due: string;
  responsible: string;
  task: string;
}

export const designIssues: DesignIssueRow[] = [
  { id: "ЗМ-041", title: "Несоответствие раздела ВК и АР по осям 3–4", source: "Нормоконтроль", severity: "Критическое", severityTone: "red", status: "В работе", statusTone: "navy", due: "22.08.2026", responsible: "Исраилова М.", task: "T-3101" },
  { id: "ЗМ-039", title: "Замечание экспертизы по узлу входной группы", source: "Экспертиза", severity: "Высокое", severityTone: "amber", status: "Открыто", statusTone: "amber", due: "25.08.2026", responsible: "Джаватова Л.", task: "T-3099" },
  { id: "ЗМ-036", title: "Пожелание заказчика по цвету фасада", source: "Заказчик", severity: "Обычное", severityTone: "gray", status: "Открыто", statusTone: "amber", due: "28.08.2026", responsible: "Умаров Т.", task: "T-3095" },
  { id: "ЗМ-030", title: "Уточнить спецификацию светильников", source: "Внутреннее", severity: "Обычное", severityTone: "gray", status: "Решено", statusTone: "emerald", due: "18.08.2026", responsible: "Джаватова Л.", task: "T-3088" },
];

export interface RealizabilityRow {
  spec: string;
  availability: string;
  availTone: GipTone;
  suppliers: number;
  minPrice: string;
  maxPrice: string;
  lead: string;
  region: boolean;
  recommended: string;
}

export const realizability: RealizabilityRow[] = [
  { spec: "Керамогранит 600×600", availability: "Доступно", availTone: "emerald", suppliers: 4, minPrice: "2 100 ₽", maxPrice: "2 600 ₽", lead: "7 дн", region: true, recommended: "ТД «Отделка+»" },
  { spec: "Светильник LED 30Вт", availability: "Ограничено", availTone: "amber", suppliers: 2, minPrice: "3 700 ₽", maxPrice: "4 200 ₽", lead: "14 дн", region: true, recommended: "«СветоТорг»" },
  { spec: "Диван для лобби (под заказ)", availability: "Под заказ", availTone: "amber", suppliers: 1, minPrice: "84 000 ₽", maxPrice: "84 000 ₽", lead: "35 дн", region: false, recommended: "«Интерьер-М»" },
  { spec: "Насос Ø50", availability: "Доступно", availTone: "emerald", suppliers: 3, minPrice: "118 000 ₽", maxPrice: "134 000 ₽", lead: "10 дн", region: true, recommended: "«ПолимерСнаб»" },
];

export const designSuppliers = [
  { name: "ТД «Отделка+»", categories: "Отделочные материалы", region: "Юг РФ", lead: "7 дн", rating: 4.6, status: "Активен" },
  { name: "«СветоТорг»", categories: "Освещение", region: "ЮФО, СКФО", lead: "14 дн", rating: 4.3, status: "Активен" },
  { name: "«Интерьер-М»", categories: "Мебель (под заказ)", region: "РФ", lead: "35 дн", rating: 4.1, status: "Активен" },
  { name: "«ПолимерСнаб»", categories: "Насосы, трубы", region: "Юг РФ", lead: "10 дн", rating: 4.2, status: "Активен" },
];
