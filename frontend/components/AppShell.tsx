"use client";

/*
 * Оболочка приложения: левая навигация + верхняя панель + адаптивное меню.
 * Статический прототип интерфейса (mock-данные), без обращения к backend.
 */
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icons, type IconName } from "../lib/icons";
import { company } from "../lib/mock";
import { logout } from "../lib/authApi";

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
      { href: "/dashboard/digest", label: "Сводка руководителю", icon: "reports" },
      { href: "/inbox", label: "Входящий поток", icon: "documents" },
      { href: "/sites", label: "Объекты и проекты", icon: "sites" },
      { href: "/tasks", label: "Задачи и сроки", icon: "tasks", badge: "9", badgeWarn: true },
      { href: "/tasks/control", label: "Контроль исполнения", icon: "approvals" },
      { href: "/approvals", label: "Согласования", icon: "approvals", badge: "5" },
    ],
  },
  {
    section: "CRM и продажи",
    items: [
      { href: "/crm", label: "Сводка и аналитика", icon: "reports" },
      { href: "/crm/leads", label: "Лиды", icon: "employees", badge: "7", badgeWarn: true },
      { href: "/crm/deals", label: "Сделки и воронка", icon: "finance" },
      { href: "/crm/counterparties", label: "Заказчики и контакты", icon: "sites" },
      { href: "/crm/communications", label: "Центр коммуникаций", icon: "documents" },
      { href: "/crm/contracts", label: "Договоры", icon: "approvals", badge: "2", badgeWarn: true },
      { href: "/crm/offers", label: "Коммерческие предложения", icon: "tasks" },
    ],
  },
  {
    section: "Финансы и бюджеты",
    items: [
      { href: "/finance", label: "Финансовая сводка", icon: "finance" },
      { href: "/finance/budget", label: "Бюджет проекта", icon: "documents" },
      { href: "/finance/commitments", label: "Обязательства", icon: "procurement", badge: "1", badgeWarn: true },
      { href: "/finance/invoices", label: "Счета к оплате", icon: "documents" },
      { href: "/finance/payment-requests", label: "Заявки на оплату", icon: "approvals", badge: "1", badgeWarn: true },
      { href: "/finance/payments", label: "Платежи", icon: "finance" },
      { href: "/finance/plan-fact", label: "План-факт", icon: "reports" },
    ],
  },
  {
    section: "Подотчётные средства",
    items: [
      { href: "/accountable", label: "Выдачи и расходы", icon: "finance" },
      { href: "/accountable/review", label: "Проверка (бухгалтер)", icon: "approvals" },
    ],
  },
  {
    section: "Операции",
    items: [
      { href: "/documents", label: "Документы", icon: "documents" },
    ],
  },
  {
    section: "Снабжение и закупки",
    items: [
      { href: "/procurement", label: "Сводка снабжения", icon: "procurement" },
      { href: "/procurement/material-flow", label: "Заявки и выдача (контур)", icon: "tasks" },
      { href: "/procurement/requests", label: "Заявки на материалы", icon: "tasks" },
      { href: "/procurement/rfq", label: "Запросы цен и КП", icon: "reports" },
      { href: "/procurement/orders", label: "Заказы поставщикам", icon: "approvals", badge: "3", badgeWarn: true },
      { href: "/procurement/receipts", label: "Поступление и приёмка", icon: "documents" },
      { href: "/procurement/stock", label: "Складской учёт (контур)", icon: "sites" },
      { href: "/procurement/warehouse", label: "Склад: остатки", icon: "sites" },
      { href: "/procurement/inventory", label: "Выдача и инвентаризация", icon: "finance" },
    ],
  },
  {
    section: "Техника и инструмент",
    items: [
      { href: "/equipment", label: "Техника, транспорт, инструмент", icon: "procurement" },
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
      { href: "/personnel/field-report", label: "Отчёт прораба (контур)", icon: "reports" },
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
      { href: "/integrations", label: "Интеграции и рассылки", icon: "documents" },
      { href: "/smm", label: "SMM и публикации", icon: "documents" },
      { href: "/risks", label: "Реестр рисков", icon: "approvals" },
      { href: "/kpi", label: "KPI и аудит", icon: "dashboard" },
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
  "/dashboard/digest": { title: "Управленческая сводка руководителю", sub: "Утренняя и вечерняя сводка на реальных данных: задачи, финансы, снабжение, склад, отчёты, риски" },
  "/inbox": { title: "Единый входящий поток", sub: "Приём, классификация и маршрутизация обращений в задачи, документы и риски" },
  "/sites": { title: "Строительные объекты и проектные работы", sub: "Портфель проектов компании" },
  "/tasks": { title: "Задачи, сроки и просрочки", sub: "Контроль исполнения поручений" },
  "/tasks/control": { title: "Контроль исполнения поручений", sub: "Просрочка, препятствия, вопросы, эскалация, возврат на доработку, уведомления" },
  "/approvals": { title: "Согласования R0–R4", sub: "Человек в контуре критических решений" },
  "/crm": { title: "CRM — сводка и аналитика продаж", sub: "Воронка, конверсия, план-факт по менеджерам" },
  "/crm/leads": { title: "Лиды", sub: "Источники, квалификация и конвертация в сделку" },
  "/crm/deals": { title: "Сделки и воронка продаж", sub: "Этапы, выигрыш R3, крупная сделка R4 + MFA" },
  "/crm/counterparties": { title: "Заказчики и контактные лица", sub: "Карточки клиентов, контакты и согласия на ПДн" },
  "/crm/communications": { title: "Единый центр коммуникаций", sub: "Письма, звонки, встречи; сообщение → задача" },
  "/crm/contracts": { title: "Договоры", sub: "Согласование R3/R4, основание для проекта" },
  "/crm/offers": { title: "Коммерческие предложения", sub: "Переиспользование commercial_offers сметного модуля" },
  "/finance": { title: "Финансы и бюджеты — сводка", sub: "Бюджет, обязательства, факт, остаток и прогноз" },
  "/finance/budget": { title: "Бюджет проекта", sub: "Статьи из сметы и ручные · утверждение R3/R4" },
  "/finance/commitments": { title: "Финансовые обязательства", sub: "Заказы, договоры и ручные обязательства" },
  "/finance/invoices": { title: "Счета к оплате", sub: "Регистрация счетов и статус оплаты" },
  "/finance/payment-requests": { title: "Заявки на оплату", sub: "Согласование R3/R4 + MFA · человек в контуре" },
  "/finance/payments": { title: "Платежи", sub: "Ручная фиксация оплат · без банковских операций" },
  "/finance/plan-fact": { title: "План-факт по проектам", sub: "Бюджет, обязательства, факт и прогноз портфеля" },
  "/accountable": { title: "Подотчётные средства", sub: "Выдача под отчёт, расходы с чеками, авансовый отчёт" },
  "/accountable/review": { title: "Проверка подотчётных расходов", sub: "Бухгалтер: проверка расходов, отчётов, возврат/возмещение" },
  "/procurement": { title: "Снабжение и закупки — сводка", sub: "Заявки, заказы, поставки, склад" },
  "/procurement/material-flow": { title: "Заявки и выдача материалов", sub: "Заявка → согласование R2–R4 → резерв → выдача → получение → возврат" },
  "/procurement/requests": { title: "Заявки на материалы", sub: "Проверка сметы и остатков, согласование R2" },
  "/procurement/rfq": { title: "Запросы цен и сравнение КП", sub: "Предложения поставщиков и выбор цены" },
  "/procurement/orders": { title: "Заказы поставщикам", sub: "Согласование R3/R4, резервирование" },
  "/procurement/receipts": { title: "Поступление и входной контроль", sub: "Приёмка, качество, оприходование" },
  "/procurement/stock": { title: "Складской учёт и остатки", sub: "Остатки, свободный остаток, резервы, точка дозаказа, журнал движений" },
  "/equipment": { title: "Техника, транспорт и инструмент", sub: "Реестр, назначение, эксплуатация, топливо, техобслуживание, инструмент" },
  "/procurement/warehouse": { title: "Склад: остатки и движения", sub: "Остатки, резервы, проводки" },
  "/procurement/inventory": { title: "Выдача и инвентаризация", sub: "Выдача на объект и сверка остатков" },
  "/documents": { title: "Документы", sub: "База знаний и документооборот" },
  "/personnel": { title: "Персонал объектов — сводка директора", sub: "Производственный учёт по всем объектам" },
  "/personnel/site": { title: "Персонал объекта", sub: "Работники, бригады, время и допуски" },
  "/personnel/timesheet": { title: "Табель рабочего времени", sub: "Смены, часы, переработки, простои" },
  "/personnel/payroll": { title: "Предварительный расчёт начислений", sub: "ФОТ · выплата только после подтверждения человека" },
  "/personnel/safety": { title: "Охрана труда и допуски", sub: "Инструктажи, медосмотры, удостоверения, допуски" },
  "/personnel/journals": { title: "Журналы прораба", sub: "Обязательные журналы и их состояние" },
  "/personnel/worker": { title: "Карточка работника на объекте", sub: "Табель, начисления, инструктажи, допуски" },
  "/personnel/field-report": { title: "Ежедневный отчёт прораба", sub: "Мобильная форма: работы, люди, техника, проблемы, фото, проверка ПТО" },
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
  "/agents": { title: "Оркестратор ИИ-агентов", sub: "Реестр агентов, запуски и предложения под утверждением человека" },
  "/integrations": { title: "Масштабирование интеграций", sub: "Реестр коннекторов и исходящие сообщения — черновики на утверждение, без отправки" },
  "/smm": { title: "SMM и внешние публикации", sub: "Контент-план и публикации — черновики на утверждение, без публикации" },
  "/kpi": { title: "KPI и независимый аудит", sub: "Объективные показатели из данных системы и находки независимого аудита" },
  "/risks": { title: "Реестр рисков", sub: "Идентификация, оценка (вероятность × влияние), снижение и принятие рисков" },
  "/reports": { title: "Отчёты и риски", sub: "Аналитика, KPI и управление рисками" },
  "/settings": { title: "Настройки", sub: "Профиль, доступ, интеграции" },
};

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/dashboard";
  const router = useRouter();
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
          <button
            className="avatar"
            title="Выйти из системы"
            onClick={async () => {
              await logout();
              router.push("/login");
            }}
            style={{ background: "none", border: "none", cursor: "pointer" }}
          >
            <div className="avatar__img">БМ</div>
            <div>
              <div className="avatar__name">{company.ceo}</div>
              <div className="avatar__role">Выйти</div>
            </div>
          </button>
        </header>

        <main className="content">{children}</main>
      </div>
    </div>
  );
}
