/* Модуль «Финансы и бюджеты». Экран 4 — план-факт по проектам. */
import { PageHead, Card } from "../../../../components/ui";
import { planFact } from "../../../../lib/finance";

export default function PlanFactPage() {
  const maxV = Math.max(...planFact.map((p) => Math.max(p.budget, p.forecast)));
  return (
    <>
      <PageHead
        title="План-факт по проектам"
        desc="Бюджет, обязательства, факт и прогноз по портфелю (агрегация без дублирования)"
        action={<button className="btn btn--ghost btn--sm">Экспорт CSV/JSON</button>}
      />

      <Card title="Бюджет · обязательства · факт · прогноз, млн ₽" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Проект</th>
                <th style={{ textAlign: "right" }}>Бюджет</th>
                <th style={{ textAlign: "right" }}>Обязательства</th>
                <th style={{ textAlign: "right" }}>Факт</th>
                <th style={{ textAlign: "right" }}>Прогноз</th>
                <th style={{ width: "26%" }}>Освоение</th>
              </tr>
            </thead>
            <tbody>
              {planFact.map((p) => {
                const pct = Math.round((p.actual / p.budget) * 100);
                const over = p.forecast > p.budget;
                return (
                  <tr key={p.project}>
                    <td className="table__strong">{p.project}</td>
                    <td style={{ textAlign: "right" }}>{p.budget.toFixed(1)}</td>
                    <td style={{ textAlign: "right" }}>{p.committed.toFixed(1)}</td>
                    <td style={{ textAlign: "right" }} className="table__strong">{p.actual.toFixed(1)}</td>
                    <td style={{ textAlign: "right", color: over ? "var(--red-600)" : "var(--emerald-700)", fontWeight: 600 }}>
                      {p.forecast.toFixed(1)}
                    </td>
                    <td>
                      <div className="progress">
                        <div className={`progress__bar${pct > 90 ? " progress__bar--amber" : ""}`} style={{ width: `${Math.min(pct, 100)}%` }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Прогноз против бюджета, млн ₽" flush className="span-2">
        <div style={{ display: "flex", alignItems: "flex-end", gap: 18, height: 180, padding: "8px 12px" }}>
          {planFact.map((p) => (
            <div key={p.project} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%", gap: 6 }}>
              <div className="row" style={{ gap: 5, alignItems: "flex-end", height: "100%" }}>
                <div title={`Бюджет: ${p.budget}`} style={{ width: 16, height: `${(p.budget / maxV) * 100}%`, background: "linear-gradient(180deg, var(--navy-500), var(--navy-700))", borderRadius: "5px 5px 0 0" }} />
                <div title={`Прогноз: ${p.forecast}`} style={{ width: 16, height: `${(p.forecast / maxV) * 100}%`, background: p.forecast > p.budget ? "linear-gradient(180deg, var(--red-500, #ef4444), var(--red-600, #dc2626))" : "linear-gradient(180deg, var(--emerald-500), var(--emerald-700))", borderRadius: "5px 5px 0 0" }} />
              </div>
              <span className="muted" style={{ fontSize: 11, textAlign: "center" }}>{p.project.split(" ").slice(0, 2).join(" ")}</span>
            </div>
          ))}
        </div>
        <div className="legend" style={{ flexDirection: "row", gap: 18, marginTop: 6, padding: "0 12px 12px" }}>
          <div className="legend__item"><span className="legend__swatch" style={{ background: "var(--navy-600)" }} /> Бюджет</div>
          <div className="legend__item"><span className="legend__swatch" style={{ background: "var(--emerald-600)" }} /> Прогноз (в норме / перерасход)</div>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          План-факт не копируется из других модулей — он <strong>агрегируется</strong>: бюджет из
          <strong> budgets</strong>, обязательства из заказов и договоров, факт из полученных заказов
          и утверждённого ФОТ. Прогноз = факт + обязательства. Экспорт в бухгалтерию — файл CSV/JSON.
        </div>
      </div>
    </>
  );
}
