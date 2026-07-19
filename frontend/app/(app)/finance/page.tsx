/* Экран 5. Финансы и бюджеты. */
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { financeKpis, budgetsBySite, cashflow, advances } from "../../../lib/mock";

export default function FinancePage() {
  const maxFlow = Math.max(...cashflow.flatMap((c) => [c.income, c.expense]));

  return (
    <>
      <PageHead
        title="Финансы и бюджеты"
        desc="План-факт по объектам, кассовый прогноз и подотчётные средства"
        action={<button className="btn btn--ghost btn--sm">Экспорт в бухгалтерию</button>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {financeKpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <div className="grid grid--2" style={{ marginBottom: 18 }}>
        <Card title="Бюджет и освоение по объектам, млн ₽">
          <div className="stack" style={{ gap: 14 }}>
            {budgetsBySite.map((b) => {
              const pct = Math.round((b.spent / b.budget) * 100);
              return (
                <div key={b.site}>
                  <div className="row row--between" style={{ marginBottom: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{b.site}</span>
                    <span className="muted" style={{ fontSize: 12.5 }}>
                      {b.spent} / {b.budget} · {pct}%
                    </span>
                  </div>
                  <div className="progress">
                    <div
                      className={`progress__bar${pct > 90 ? " progress__bar--amber" : ""}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card title="Доходы и расходы, млн ₽" more="Кассовый прогноз">
          <div className="mini-bars" style={{ height: 150, alignItems: "flex-end" }}>
            {cashflow.map((c) => (
              <div key={c.m} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, height: "100%", justifyContent: "flex-end" }}>
                <div className="row" style={{ gap: 4, alignItems: "flex-end", height: "100%" }}>
                  <div style={{ width: 14, height: `${(c.income / maxFlow) * 100}%`, background: "linear-gradient(180deg, var(--navy-500), var(--navy-700))", borderRadius: "5px 5px 0 0" }} title={`Доход: ${c.income}`} />
                  <div style={{ width: 14, height: `${(c.expense / maxFlow) * 100}%`, background: "linear-gradient(180deg, var(--emerald-500), var(--emerald-700))", borderRadius: "5px 5px 0 0" }} title={`Расход: ${c.expense}`} />
                </div>
                <span className="muted" style={{ fontSize: 11 }}>{c.m}</span>
              </div>
            ))}
          </div>
          <div className="legend" style={{ flexDirection: "row", gap: 18, marginTop: 14 }}>
            <div className="legend__item"><span className="legend__swatch" style={{ background: "var(--navy-600)" }} /> Доход</div>
            <div className="legend__item"><span className="legend__swatch" style={{ background: "var(--emerald-600)" }} /> Расход</div>
          </div>
        </Card>
      </div>

      <Card title="Подотчётные средства" more="Все операции" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Сотрудник</th>
                <th>Объект</th>
                <th>Выдано</th>
                <th>Израсходовано</th>
                <th>Остаток</th>
                <th>Срок отчёта</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {advances.map((a) => (
                <tr key={a.person}>
                  <td className="table__strong">{a.person}</td>
                  <td>{a.site}</td>
                  <td>{a.issued}</td>
                  <td>{a.spent}</td>
                  <td style={{ color: a.tone === "red" ? "var(--red-600)" : "var(--emerald-700)", fontWeight: 600 }}>
                    {a.balance}
                  </td>
                  <td>{a.due}</td>
                  <td>
                    <Badge tone={a.tone}>{a.tone === "red" ? "Перерасход" : "В норме"}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
