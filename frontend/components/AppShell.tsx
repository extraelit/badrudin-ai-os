"use client";

/*
 * Оболочка приложения: левая навигация + верхняя панель + адаптивное меню.
 * Статический прототип интерфейса (mock-данные), без обращения к backend.
 */
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icons, type IconName } from "../lib/icons";
import { company } from "../lib/mock";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  badge?: string;
  badgeWarn?: boolean;
}

interface NavGroup {
  section: string;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    section: "Основное",
    items: [
      { href: "/dashboard", label: "Панель директора", icon: "dashboard" },
      { href: "/sites", label: "Объекты и проекты", icon: "sites" },
      { href: "/tasks", label: "Задачи и сроки", icon: "tasks", badge: "9", badgeWarn: true },
      { href: "/approvals", label: "Согласования", icon: "approvals", badge: "5" },
    ],
  },
  {
    section: "Операции",
    items: [
      { href: "/finance", label: "Финансы и бюджеты", icon: "finance" },
      { href: "/procurement", label: "Снабжение и закупки", icon: "procurement" },
      { href: "/documents", label: "Документы", icon: "documents" },
    ],
  },
  {
    section: "Персонал объектов",
    items: [
      { href: "/personnel", label: "Сводка по объектам", icon: "employees" },
      { href: "/personnel/site", label: "Карточка объекта", icon: "sites" },
      { href: "/personnel/timesheet", label: "Табель времени", icon: "clock" },
      { href: "/personnel/payroll", label: "Начисления (ФОТ)", icon: "finance" },
      { href: "/personnel/safety", label: "Охрана труда", icon: "approvals", badge: "7", badgeWarn: true },
      { href: "/personnel/journals", label: "Журналы прораба", icon: "documents" },
      { href: "/personnel/worker", label: "Карточка работника", icon: "employees" },
      { href: "/personnel/daily-report", label: "Отчёт прораба", icon: "reports" },
    ],
  },
  {
    section: "Проектирование и дизайн",
    items: [
      { href: "/design", label: "Рабочее пространство", icon: "dashboard" },
      { href: "/design/disciplines", label: "ГИП — разделы", icon: "tasks" },
      { href: "/design/brief", label: "Техническое задание", icon: "documents" },
      { href: "/design/concepts", label: "Концепции", icon: "reports" },
      { href: "/design/specifications", label: "Спецификации", icon: "procurement" },
      { href: "/design/issues", label: "Замечания", icon: "approvals", badge: "11", badgeWarn: true },
      { href: "/design/realizability", label: "Реализуемость", icon: "finance" },
    ],
  },
  {
    section: "Сметы и ценообразование",
    items: [
      { href: "/estimates", label: "Сводка смет", icon: "finance" },
      { href: "/estimates/editor", label: "Смета и позиции", icon: "documents" },
      { href: "/estimates/volumes", label: "Ведомость объёмов", icon: "tasks" },
      { href: "/estimates/rates", label: "Расценки и цены", icon: "procurement" },
      { href: "/estimates/offers", label: "Коммерческие предложения", icon: "approvals" },
      { href: "/estimates/plan-fact", label: "План-факт", icon: "reports" },
      { href: "/estimates/changes", label: "Изменения сметы", icon: "clock" },
    ],
  },
  {
    section: "Организация",
    items: [
      { href: "/employees", label: "Сотрудники", icon: "employees" },
      { href: "/agents", label: "ИИ-агенты", icon: "agents" },
      { href: "/reports", label: "Отчёты и риски", icon: "reports" },
    ],
  },
  {
    section: "Система",
    items: [{ href: "/settings", label: "Настройки", icon: "settings" }],
  },
];

const TITLES: Record<string, { title: string; sub: string }> = {
  "/dashboard": { title: "Панель генерального директора", sub: "Единый центр управления · 19 июля 2026" },
  "/sites": { title: "Строительные объекты и проектные работы", sub: "Портфель проектов компании" },
  "/tasks": { title: "Задачи, сроки и просрочки", sub: "Контроль исполнения поручений" },
  "/approvals": { title: "Согласования R0–R4", sub: "Человек в контуре критических решений" },
  "/finance": { title: "Финансы и бюджеты", sub: "План-факт, кассовый прогноз, подотчётные" },
  "/procurement": { title: "Снабжение и закупки", sub: "Заявки, поставки, поставщики" },
  "/documents": { title: "Документы", sub: "База знаний и документооборот" },
  "/personnel": { title: "Персонал объектов — сводка директора", sub: "Производственный учёт по всем объектам" },
  "/personnel/site": { title: "Персонал объекта", sub: "Работники, бригады, время и допуски" },
  "/personnel/timesheet": { title: "Табель рабочего времени", sub: "Смены, часы, переработки, простои" },
  "/personnel/payroll": { title: "Предварительный расчёт начислений", sub: "ФОТ · выплата только после подтверждения человека" },
  "/personnel/safety": { title: "Охрана труда и допуски", sub: "Инструктажи, медосмотры, удостоверения, допуски" },
  "/personnel/journals": { title: "Журналы прораба", sub: "Обязательные журналы и их состояние" },
  "/personnel/worker": { title: "Карточка работника на объекте", sub: "Табель, начисления, инструктажи, допуски" },
  "/personnel/daily-report": { title: "Ежедневный отчёт прораба", sub: "Численность, объёмы, техника, происшествия" },
  "/design": { title: "Проектирование и дизайн", sub: "Рабочее пространство проекта и ГИП" },
  "/design/disciplines": { title: "ГИП — статус разделов", sub: "Комплектность, готовность и проверка" },
  "/design/brief": { title: "Техническое задание / бриф", sub: "Требования, бюджет и срок" },
  "/design/concepts": { title: "Концепции и версии", sub: "Дизайн-концепции и обратная связь заказчика" },
  "/design/specifications": { title: "Спецификации и ведомости", sub: "Материалы, поставщики, аналоги" },
  "/design/issues": { title: "Реестр замечаний", sub: "Замечания → задачи с ответственными" },
  "/design/realizability": { title: "Проверка реализуемости", sub: "Наличие, цены, сроки, поставщики" },
  "/estimates": { title: "Сметы и ценообразование — сводка", sub: "Сметный отдел: сметы, отклонения, КП" },
  "/estimates/editor": { title: "Смета и позиции", sub: "Материалы, труд, машины · накладные, прибыль, НДС" },
  "/estimates/volumes": { title: "Ведомость объёмов работ", sub: "План и факт объёмов, проверка" },
  "/estimates/rates": { title: "Расценки и цены", sub: "Справочник расценок и цены поставщиков" },
  "/estimates/offers": { title: "Коммерческие предложения", sub: "Наценка, итоговая цена, R3/R4" },
  "/estimates/plan-fact": { title: "План-факт анализ", sub: "Объёмы и стоимость, прогноз, отклонения" },
  "/estimates/changes": { title: "Изменения сметы", sub: "Версии, change order, причины изменений" },
  "/employees": { title: "Сотрудники и структура организации", sub: "Кадры и подразделения" },
  "/agents": { title: "ИИ-агенты и их статусы", sub: "Режимы работы и человек в контуре" },
  "/reports": { title: "Отчёты и риски", sub: "Аналитика, KPI и управление рисками" },
  "/settings": { title: "Настройки", sub: "Профиль, доступ, интеграции" },
};

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/dashboard";
  const [open, setOpen] = useState(false);
  const meta = TITLES[pathname] ?? { title: company.system, sub: company.name };

  // Активной считается ссылка с самым длинным совпадающим префиксом,
  // чтобы вложенные маршруты (/personnel/site) не подсвечивали /personnel.
  const allHrefs = NAV.flatMap((g) => g.items.map((i) => i.href));
  const activeHref = allHrefs
    .filter((h) => pathname === h || pathname.startsWith(h + "/"))
    .sort((a, b) => b.length - a.length)[0];

  return (
    <div className="app">
      <aside className={`sidebar${open ? " sidebar--open" : ""}`}>
        <div className="sidebar__brand">
          <div className="sidebar__logo">B</div>
          <div>
            <div className="sidebar__brand-title">Badrudin AI OS</div>
            <div className="sidebar__brand-sub">ООО «Экстра-Элит»</div>
          </div>
        </div>

        <nav className="sidebar__nav">
          {NAV.map((group) => (
            <div key={group.section}>
              <div className="sidebar__section">{group.section}</div>
              {group.items.map((item) => {
                const Icon = Icons[item.icon];
                const active = item.href === activeHref;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`navlink${active ? " navlink--active" : ""}`}
                    onClick={() => setOpen(false)}
                  >
                    <Icon className="navlink__icon" />
                    <span>{item.label}</span>
                    {item.badge && (
                      <span
                        className={`navlink__badge${item.badgeWarn ? " navlink__badge--warn" : ""}`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar__foot">
          Демо-версия интерфейса · mock-данные.<br />
          Реальные данные и production не подключены.
        </div>
      </aside>

      <div
        className={`overlay${open ? " overlay--show" : ""}`}
        onClick={() => setOpen(false)}
      />

      <div className="main">
        <header className="topbar">
          <button
            className="topbar__burger"
            aria-label="Меню"
            onClick={() => setOpen((v) => !v)}
          >
            <Icons.menu />
          </button>
          <div>
            <div className="topbar__title">{meta.title}</div>
            <div className="topbar__sub">{meta.sub}</div>
          </div>
          <div className="topbar__spacer" />
          <div className="searchbox">
            <Icons.search width={16} height={16} />
            <input placeholder="Поиск по объектам, задачам…" />
          </div>
          <button className="topbar__icon-btn" aria-label="Уведомления">
            <Icons.bell width={19} height={19} />
            <span className="dot" />
          </button>
          <Link href="/login" className="avatar" title="Выйти в демо-вход">
            <div className="avatar__img">БМ</div>
            <div>
              <div className="avatar__name">{company.ceo}</div>
              <div className="avatar__role">{company.role}</div>
            </div>
          </Link>
        </header>

        <main className="content">{children}</main>
      </div>
    </div>
  );
}
