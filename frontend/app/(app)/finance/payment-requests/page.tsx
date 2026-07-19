/* Модуль «Финансы и бюджеты». Экран 6 — заявки на оплату. */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { payRequests } from "../../../../lib/finance";

export default function PaymentRequestsPage() {
  return (
    <>
      <PageHead
        title="Заявки на оплату"
        desc="Согласование оплаты счёта: R3, крупная сумма — R4 + MFA; человек в контуре"
      />

      <Card title="Заявки на оплату" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Счёт</th>
                <th>Контрагент</th>
                <th style={{ textAlign: "right" }}>Сумма, ₽</th>
                <th>План. дата</th>
                <th>Риск</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {payRequests.map((p) => (
                <tr key={p.id}>
                  <td className="table__muted">{p.id}</td>
                  <td className="table__muted">{p.invoice}</td>
                  <td className="table__strong">{p.counterparty}</td>
                  <td style={{ textAlign: "right" }} className="table__strong">{p.amount}</td>
                  <td className="table__muted">{p.planned}</td>
                  <td><Risk level={p.risk} /></td>
                  <td><Badge tone={p.statusTone}>{p.status}</Badge></td>
                  <td>
                    {p.status === "На согласовании" ? (
                      <button className="btn btn--emerald btn--sm">{p.risk === "R4" ? "Утвердить + MFA" : "Утвердить"}</button>
                    ) : p.status === "Согласована" ? (
                      <button className="btn btn--ghost btn--sm">Провести платёж</button>
                    ) : (
                      <span className="muted" style={{ fontSize: 12 }}>—</span>
                    )}
                  </td>
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
          Заявка на оплату (<strong>payment_requests</strong>) проходит согласование через общий
          контур <strong>approvals</strong>: <strong>R3</strong> — обычная сумма, <strong>R4 + MFA</strong> —
          крупная (порог организации, по умолчанию 10 млн ₽). Согласованная заявка — основание для
          ручной фиксации платежа. ИИ и система платёж не проводят.
        </div>
      </div>
    </>
  );
}
