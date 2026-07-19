/* Модуль «Ядро CRM». Экран 3 — сделки: воронка (канбан) и список. */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { deals, kanban } from "../../../../lib/crm";

export default function DealsPage() {
  return (
    <>
      <PageHead
        title="Сделки и воронка"
        desc="Движение по этапам; выигрыш — R3, крупная сделка — R4 + MFA"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новая сделка</button>}
      />

      <Card title="Воронка (канбан)" flush className="span-2">
        <div style={{ display: "flex", gap: 14, overflowX: "auto", padding: "4px 2px 8px" }}>
          {kanban.map((col) => (
            <div key={col.stage} style={{ minWidth: 230, flex: "0 0 230px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span className="table__strong" style={{ fontSize: 13 }}>{col.stage}</span>
                <span className="badge badge--gray">{col.probability}%</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {col.cards.map((c) => (
                  <div key={c.id} className="card" style={{ padding: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span className="table__muted" style={{ fontSize: 12 }}>{c.id}</span>
                      <Risk level={c.risk} />
                    </div>
                    <div className="table__strong" style={{ margin: "6px 0 2px", fontSize: 13 }}>{c.title}</div>
                    <div className="muted" style={{ fontSize: 12 }}>{c.client}</div>
                    <div className="table__strong" style={{ marginTop: 8, color: "var(--emerald-600)" }}>{c.amount}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Все сделки" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Сделка</th>
                <th>Заказчик</th>
                <th>Сумма</th>
                <th>Этап</th>
                <th>Ответственный</th>
                <th>Закрытие</th>
                <th>Риск</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {deals.map((d) => (
                <tr key={d.id}>
                  <td className="table__muted">{d.id}</td>
                  <td className="table__strong">{d.title}</td>
                  <td>{d.client}</td>
                  <td className="table__strong">{d.amount}</td>
                  <td>{d.stage}</td>
                  <td>{d.responsible}</td>
                  <td className="table__muted">{d.close}</td>
                  <td><Risk level={d.risk} /></td>
                  <td><Badge tone={d.statusTone}>{d.status}</Badge></td>
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
          Этапы воронки настраиваются (<strong>pipeline_stages</strong>): порядок, вероятность,
          признаки выигранного и проигранного этапа. Перевод в «Выиграна» и подписание договора —
          <strong> R3</strong>; крупная сделка (порог организации, по умолчанию 10 млн ₽) —
          <strong> R4 + MFA</strong>. Все переходы фиксируются в аудите.
        </div>
      </div>
    </>
  );
}
