/* Модуль «Финансы и бюджеты». Экран 7 — платежи. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { payments } from "../../../../lib/finance";

export default function PaymentsPage() {
  return (
    <>
      <PageHead
        title="Платежи"
        desc="Ручная фиксация проведённых платежей; идемпотентность повторного ввода"
        action={<button className="btn btn--ghost btn--sm">Экспорт CSV/JSON</button>}
      />

      <Card title="Проведённые платежи" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Счёт</th>
                <th>Контрагент</th>
                <th style={{ textAlign: "right" }}>Сумма, ₽</th>
                <th>Дата</th>
                <th>Способ</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id}>
                  <td className="table__muted">{p.id}</td>
                  <td className="table__muted">{p.invoice}</td>
                  <td className="table__strong">{p.counterparty}</td>
                  <td style={{ textAlign: "right" }} className="table__strong">{p.amount}</td>
                  <td className="table__muted">{p.date}</td>
                  <td>{p.method}</td>
                  <td><Badge tone={p.statusTone}>{p.status}</Badge></td>
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
          Платёж (<strong>payments</strong>) — это <strong>отражение</strong> проведённой оплаты, а
          не банковская операция: он вводится вручную либо импортируется из бухгалтерии. Повторный
          ввод с тем же ключом идемпотентности не задваивает оплату. Платёж уменьшает остаток к
          оплате по счёту и обновляет его статус.
        </div>
      </div>
    </>
  );
}
