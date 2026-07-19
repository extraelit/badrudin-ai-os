/* Модуль «Финансы и бюджеты». Экран 3 — финансовые обязательства. */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { commitments } from "../../../../lib/finance";

export default function CommitmentsPage() {
  return (
    <>
      <PageHead
        title="Финансовые обязательства"
        desc="Заказы и договоры агрегируются автоматически; ручные обязательства — для решений вне заказов"
        action={<button className="btn btn--ghost btn--sm"><Icons.plus width={16} height={16} /> Ручное обязательство</button>}
      />

      <Card title="Обязательства проекта" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Назначение</th>
                <th>Контрагент</th>
                <th style={{ textAlign: "right" }}>Сумма, ₽</th>
                <th>Источник</th>
                <th>Срок</th>
                <th>Риск</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {commitments.map((c) => (
                <tr key={c.id}>
                  <td className="table__muted">{c.id}</td>
                  <td className="table__strong">{c.description}</td>
                  <td>{c.counterparty}</td>
                  <td style={{ textAlign: "right" }} className="table__strong">{c.amount}</td>
                  <td><Badge tone={c.originTone}>{c.origin}</Badge></td>
                  <td className="table__muted">{c.due}</td>
                  <td><Risk level={c.risk} /></td>
                  <td><Badge tone={c.statusTone}>{c.status}</Badge></td>
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
          Обязательства по заказам (<strong>purchase_orders</strong>) и расходным договорам
          (<strong>contracts</strong>) агрегируются сервисом финансовой сводки напрямую, без
          копирования сумм. Отдельно хранятся только ручные обязательства-«решения»
          (<strong>financial_commitments</strong>) — аренда, разовые решения. Крупное обязательство
          (порог организации, по умолчанию 10 млн ₽) требует R4 + MFA.
        </div>
      </div>
    </>
  );
}
