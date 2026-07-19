/* Модуль «Персонал объектов». Экран 4 — предварительный расчёт начислений (ФОТ). */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { payroll, payrollTotals, payrollStages } from "../../../../lib/personnel";

export default function PayrollPage() {
  return (
    <>
      <PageHead
        title="Предварительный расчёт начислений"
        desc="Схемы: почасовая, посменная, окладная, сдельная · объект «Северный коллектор», июль 2026"
        action={<button className="btn btn--ghost btn--sm">Экспорт в бухгалтерию</button>}
      />

      <Card title="Этапы согласования начислений" style={{ marginBottom: 0 }}>
        <div className="grid grid--kpi" style={{ gap: 12 }}>
          {payrollStages.map((st, i) => (
            <div key={st} className="row" style={{ gap: 10, padding: 12, border: "1px solid var(--border)", borderRadius: 10 }}>
              <span className="risk risk--r2">{i + 1}</span>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{st}</span>
            </div>
          ))}
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Начисления по работникам" more="Табель" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Работник</th>
                <th>Схема</th>
                <th>Ставка</th>
                <th>Количество</th>
                <th>Начислено</th>
                <th>Аванс</th>
                <th>Удержания</th>
                <th>К выплате</th>
                <th>Статус</th>
                <th>Риск</th>
              </tr>
            </thead>
            <tbody>
              {payroll.map((p) => (
                <tr key={p.worker}>
                  <td>
                    <div className="table__strong">{p.worker}</div>
                    <div className="table__muted">{p.profession}</div>
                  </td>
                  <td><span className="badge badge--navy">{p.scheme}</span></td>
                  <td>{p.rate}</td>
                  <td>{p.qty}</td>
                  <td className="table__strong">{p.accrued}</td>
                  <td className="table__muted">{p.advance}</td>
                  <td className="table__muted">{p.deduction}</td>
                  <td className="table__strong" style={{ color: "var(--emerald-700)" }}>{p.toPay}</td>
                  <td><Badge tone={p.statusTone}>{p.status}</Badge></td>
                  <td><Risk level={p.risk} /></td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ background: "var(--surface-2)" }}>
                <td className="table__strong" colSpan={4}>Итого по объекту</td>
                <td className="table__strong">{payrollTotals.accrued}</td>
                <td>{payrollTotals.advance}</td>
                <td>{payrollTotals.deduction}</td>
                <td className="table__strong" style={{ color: "var(--emerald-700)" }}>{payrollTotals.toPay}</td>
                <td colSpan={2}></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="alert alert--danger">
        <div className="alert__icon">⚠</div>
        <div>
          <div className="table__strong">Окончательная выплата — только после подтверждения человека</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            Расчёт носит предварительный характер. Проведение выплаты требует согласования уровня
            <strong> R3</strong> (обычные суммы) или <strong> R4</strong> (крупные суммы / массовая выплата)
            с усиленной аутентификацией и записью в журнал аудита. ИИ только готовит расчёт и выявляет
            аномалии, но не проводит платежи.
          </div>
        </div>
      </div>
    </>
  );
}
