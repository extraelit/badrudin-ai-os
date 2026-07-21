"use client";

/* Модуль «Финансы и бюджеты». Экран 1 — финансовая сводка.
 * По умолчанию mock; при доступном backend подмешивается живая сводка проекта. */
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { finKpis, projectSummary } from "../../../lib/finance";
import { financeApi } from "../../../lib/financeApi";
import { coreApi } from "../../../lib/coreApi";

export default function FinanceOverviewPage() {
  const [kpis] = useState(finKpis);
  const [sum, setSum] = useState(projectSummary);
  const [live, setLive] = useState(false);

  useEffect(() => {
    // Живая сводка считается по реальному проекту (id — UUID). Берём первый
    // доступный пользователю проект; если проектов нет, живой вызов не делаем
    // (иначе backend вернёт 422 на нечисловой id).
    coreApi
      .listProjects()
      .then((projects) => {
        const projectId = projects[0]?.id;
        if (!projectId) return;
        return financeApi.getSummary(projectId).then((s) => {
          setSum((prev) => ({
            ...prev,
            approvedBudget: s.approved_budget,
            committed: s.committed,
            actual: s.actual,
            remaining: s.remaining,
            forecast: s.forecast,
            deviation: s.forecast_deviation,
          }));
          setLive(true);
        });
      })
      .catch(() => setLive(false));
  }, []);

  return (
    <>
      <PageHead
        title="Финансы и бюджеты — сводка"
        desc={"Бюджет, обязательства, факт, остаток и прогноз по проекту" + (live ? " · данные из backend" : "")}
        action={<Link href="/finance/budget" className="btn btn--primary btn--sm">Открыть бюджет</Link>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {kpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <Card title={`Финансовая сводка проекта — ${projectSummary.project}`} flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Показатель</th>
                <th style={{ textAlign: "right" }}>Сумма, ₽</th>
                <th>Комментарий</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="table__strong">Утверждённый бюджет</td>
                <td style={{ textAlign: "right" }} className="table__strong">{sum.approvedBudget}</td>
                <td className="muted">план из утверждённой сметы</td>
              </tr>
              <tr>
                <td>Обязательства</td>
                <td style={{ textAlign: "right" }}>{sum.committed}</td>
                <td className="muted">заказы + договоры + ручные</td>
              </tr>
              <tr>
                <td>Фактические затраты</td>
                <td style={{ textAlign: "right" }}>{sum.actual}</td>
                <td className="muted">получено + ФОТ</td>
              </tr>
              <tr>
                <td className="table__strong">Остаток бюджета</td>
                <td style={{ textAlign: "right", color: "var(--emerald-700)" }} className="table__strong">{sum.remaining}</td>
                <td className="muted">бюджет − факт</td>
              </tr>
              <tr>
                <td className="table__strong">Прогноз затрат</td>
                <td style={{ textAlign: "right" }} className="table__strong">{sum.forecast}</td>
                <td className="muted">факт + обязательства</td>
              </tr>
              <tr>
                <td>Отклонение прогноза</td>
                <td style={{ textAlign: "right" }}><Badge tone={sum.deviationTone}>{sum.deviation}</Badge></td>
                <td className="muted">прогноз − бюджет</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="grid grid--2">
        <Card title="Обязательства — структура" flush>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Источник</th><th style={{ textAlign: "right" }}>Сумма, ₽</th></tr></thead>
              <tbody>
                {sum.committedBreakdown.map((c) => (
                  <tr key={c.source}>
                    <td>{c.label} <span className="muted" style={{ fontSize: 11 }}>· {c.source}</span></td>
                    <td style={{ textAlign: "right" }} className="table__strong">{c.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Факт — структура" flush>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Источник</th><th style={{ textAlign: "right" }}>Сумма, ₽</th></tr></thead>
              <tbody>
                {sum.actualBreakdown.map((c) => (
                  <tr key={c.source}>
                    <td>{c.label} <span className="muted" style={{ fontSize: 11 }}>· {c.source}</span></td>
                    <td style={{ textAlign: "right" }} className="table__strong">{c.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Сводка <strong>агрегирует существующие данные без дублирования</strong>: план — из
          утверждённого бюджета (сметы), обязательства — из <strong>purchase_orders</strong>,
          расходных <strong>contracts</strong> и ручных <strong>financial_commitments</strong>,
          факт — из полученных заказов и утверждённого <strong>payroll</strong>. Экспорт в
          бухгалтерию — CSV/JSON. Подотчётные средства — отдельный будущий модуль.
        </div>
      </div>
    </>
  );
}
