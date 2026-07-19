"use client";

/* «Управленческие сводки руководителю» — рабочий контур (backend /management).
 * Утренняя и вечерняя сводка по организации на реальных данных: проекты, задачи,
 * просрочки, препятствия, согласования, финансы, снабжение, склад, отчёты
 * прорабов, риски. Данные из backend, без mock; без backend — пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge, Risk } from "../../../../components/ui";
import { apiBaseConfigured } from "../../../../lib/authApi";
import { managementApi, type Digest } from "../../../../lib/managementApi";

const TR: Record<string, string> = {
  purchase_order_approval: "Заказ поставщику",
  write_off_approval: "Списание",
  material_request_approval: "Заявка на материалы",
  daily_report_review: "Отчёт прораба",
  budget_approval: "Бюджет",
  payment_request_approval: "Оплата счёта",
  task_approval: "Поручение",
};

export default function DigestPage() {
  const live = apiBaseConfigured();
  const [kind, setKind] = useState<"morning" | "evening">(new Date().getHours() < 15 ? "morning" : "evening");
  const [d, setD] = useState<Digest | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!live) return;
    managementApi.digest(kind).then(setD).catch((e) => setErr((e as Error).message));
  }, [live, kind]);

  if (!live) {
    return (
      <>
        <PageHead title="Управленческая сводка" desc="Утренняя и вечерняя сводка руководителю" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Управленческая сводка руководителю"
        desc={d ? `${d.period_label} · ${new Date(d.generated_at).toLocaleString("ru-RU")} · данные из backend` : "Сводка по организации на реальных данных"}
        action={
          <div style={{ display: "flex", gap: 6 }}>
            <button className={`btn btn--sm ${kind === "morning" ? "btn--primary" : "btn--ghost"}`} onClick={() => setKind("morning")}>Утренняя</button>
            <button className={`btn btn--sm ${kind === "evening" ? "btn--primary" : "btn--ghost"}`} onClick={() => setKind("evening")}>Вечерняя</button>
          </div>
        }
      />
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      {d && (
        <>
          <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
            <Kpi label="Активные проекты" value={String(d.projects_active)} icon="sites" tone="navy" foot="в работе" />
            <Kpi label="Просрочено" value={String(d.tasks.overdue ?? 0)} icon="approvals" tone={d.tasks.overdue ? "amber" : "emerald"} foot={`заблокировано: ${d.tasks.blocked ?? 0}`} />
            <Kpi label="Требуют согласования" value={String(d.approvals_pending)} icon="approvals" tone={d.approvals_pending ? "amber" : "emerald"} foot="ожидают решения" />
            <Kpi label={kind === "evening" ? "Выполнено за день" : "На проверке"} value={String(kind === "evening" ? (d.tasks.completed_today ?? 0) : (d.tasks.pending_review ?? 0))} icon="reports" tone="emerald" foot={kind === "evening" ? "закрыто сегодня" : "ждут проверки"} />
          </div>

          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14, marginBottom: 18 }}>
            <Card title="Задачи и контроль" flush>
              <div style={{ padding: 12 }}>
                {rows([
                  ["В работе", d.tasks.in_progress], ["Просрочено", d.tasks.overdue],
                  ["Заблокировано", d.tasks.blocked], ["Ждут информации", d.tasks.waiting],
                  ["На проверке", d.tasks.pending_review], ["На доработке", d.tasks.returned_for_revision],
                  ...(kind === "evening" ? [["Выполнено сегодня", d.tasks.completed_today] as [string, number]] : []),
                ])}
              </div>
            </Card>
            <Card title="Риски" flush>
              <div style={{ padding: 12 }}>
                {rows([
                  ["Просрочки", d.risks.overdue], ["Препятствия", d.risks.blocked],
                  ["Высокий риск (R3–R4)", d.risks.high_risk_tasks],
                  ["Проблемы в отчётах", d.risks.high_severity_issues],
                ])}
              </div>
            </Card>
            <Card title="Финансы и снабжение" flush>
              <div style={{ padding: 12 }}>
                {rows([
                  ["Заявки на оплату", d.finance.payment_requests_pending],
                  ["Бюджеты на согласовании", d.finance.budgets_pending],
                  ["Заявки на материалы", d.procurement.requests_open],
                  ["Заказы на согласовании", d.procurement.orders_pending],
                  ["Списания на согласовании", d.procurement.writeoffs_pending],
                ])}
              </div>
            </Card>
            <Card title="Склад" flush>
              <div style={{ padding: 12 }}>
                {rows([
                  ["Позиций на складах", d.warehouse.positions],
                  ["Ниже точки дозаказа", d.warehouse.low_stock],
                  ["Отрицательный остаток", d.warehouse.negative_stock],
                ])}
                <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 13 }}>
                  <span className="muted">Стоимость запаса</span><span className="table__strong">{d.warehouse.total_value} ₽</span>
                </div>
              </div>
            </Card>
            <Card title="Отчёты прорабов" flush>
              <div style={{ padding: 12 }}>
                {rows([
                  ["На проверке", d.field_reports.submitted],
                  ["На доработке", d.field_reports.correction_required],
                  ["Сдано сегодня", d.field_reports.submitted_today],
                ])}
              </div>
            </Card>
            <Card title="Подотчётные средства" flush>
              <div style={{ padding: 12 }}>
                {rows([
                  ["Открытые выдачи", d.accountable.advances_open],
                  ["Просрочен отчёт", d.accountable.advances_overdue],
                ])}
                <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 13 }}>
                  <span className="muted">К закрытию</span><span className="table__strong">{d.accountable.outstanding} ₽</span>
                </div>
              </div>
            </Card>
          </div>

          <Card title="Требуют согласования" flush className="span-2">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Тип</th><th>Объект</th></tr></thead>
                <tbody>
                  {d.approvals.length === 0 && <tr><td colSpan={2} className="muted" style={{ padding: 16 }}>Нет действий на согласовании.</td></tr>}
                  {d.approvals.map((a) => (
                    <tr key={a.id}>
                      <td className="table__strong">{TR[a.approval_type] || a.approval_type}</td>
                      <td className="table__muted">{a.entity_type} · {a.entity_id.slice(0, 8)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div style={{ height: 18 }} />
          <Card title="Ключевые просрочки" flush className="span-2">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Поручение</th><th>Статус</th><th>Риск</th><th>Срок</th><th>Эскалация</th></tr></thead>
                <tbody>
                  {d.top_overdue.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Просрочек нет.</td></tr>}
                  {d.top_overdue.map((t) => (
                    <tr key={t.id}>
                      <td className="table__strong">{t.title}</td>
                      <td><Badge tone="amber">{t.status}</Badge></td>
                      <td><Risk level={t.risk_level as "R0" | "R1" | "R2" | "R3" | "R4"} /></td>
                      <td className="table__muted">{t.due_at ? new Date(t.due_at).toLocaleDateString("ru-RU") : "—"}</td>
                      <td>{t.escalation_level > 0 ? <Badge tone="red">{t.escalation_level}</Badge> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Сводка формируется на реальных данных модулей (задачи, контроль исполнения, финансы,
          снабжение, склад, отчёты прорабов, подотчётные средства) и ничего не изменяет. Доступ —
          управленческая роль (<strong>management.view</strong>); задачи ограничены доступными
          проектами. Утренняя сводка — что требует внимания сегодня; вечерняя — итоги дня.
        </div>
      </div>
    </>
  );
}

function rows(items: [string, number | string | undefined][]) {
  return items.map(([label, value]) => (
    <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 13, borderBottom: "1px solid var(--line,#f1f5f9)" }}>
      <span className="muted">{label}</span>
      <span className="table__strong">{value ?? 0}</span>
    </div>
  ));
}
