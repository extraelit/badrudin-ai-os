/* Модуль «Сметы и ценообразование». Экран 6 — план-факт анализ. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { planFact, planFactTotals } from "../../../../lib/estimates";

export default function PlanFactPage() {
  return (
    <>
      <PageHead
        title="План-факт анализ"
        desc="Сопоставление плановых и фактических объёмов и стоимости; прогноз итоговой стоимости"
        action={<button className="btn btn--ghost btn--sm">Экспорт отчёта</button>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">План (по факту работ)</div><div className="kpi__value" style={{ fontSize: 22 }}>{planFactTotals.planned}</div></div>
        <div className="kpi"><div className="kpi__label">Факт освоено</div><div className="kpi__value" style={{ fontSize: 22, color: "var(--emerald-600)" }}>{planFactTotals.actual}</div></div>
        <div className="kpi"><div className="kpi__label">Прогноз итоговой стоимости</div><div className="kpi__value" style={{ fontSize: 22 }}>{planFactTotals.forecast}</div></div>
        <div className="kpi"><div className="kpi__label">Отклонение</div><div className="kpi__value" style={{ fontSize: 22, color: "var(--amber-600)" }}>{planFactTotals.deviation}</div></div>
      </div>

      <Card title="План-факт по позициям (объёмы и стоимость)" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Позиция</th>
                <th>Объём план</th>
                <th>Объём факт</th>
                <th>Стоимость план</th>
                <th>Стоимость факт</th>
                <th>Отклонение</th>
              </tr>
            </thead>
            <tbody>
              {planFact.map((r) => (
                <tr key={r.position}>
                  <td className="table__strong">{r.position}</td>
                  <td>{r.plannedQty}</td>
                  <td>{r.actualQty}</td>
                  <td>{r.plannedTotal}</td>
                  <td className="table__strong">{r.actualTotal}</td>
                  <td><Badge tone={r.devTone}>{r.deviation}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          План формируется из утверждённой сметы (baseline), факт — из проверенных объёмов
          (daily_report_work_items), затрат на труд (payroll) и цен поставщиков. Директору
          показываются отклонения, прогнозная итоговая стоимость, требуемые согласования и просрочки.
        </div>
      </div>
    </>
  );
}
