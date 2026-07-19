/* Модуль «Финансы и бюджеты». Экран 5 — счета к оплате. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { invoices, payables } from "../../../../lib/finance";

export default function InvoicesPage() {
  return (
    <>
      <PageHead
        title="Счета к оплате"
        desc="Регистрация счетов от контрагентов; основание для заявки на оплату"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новый счёт</button>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Выставлено</div><div className="kpi__value" style={{ fontSize: 22 }}>{payables.invoiced} ₽</div></div>
        <div className="kpi"><div className="kpi__label">Согласовано к оплате</div><div className="kpi__value" style={{ fontSize: 22 }}>{payables.approved} ₽</div></div>
        <div className="kpi"><div className="kpi__label">Оплачено</div><div className="kpi__value" style={{ fontSize: 22, color: "var(--emerald-700)" }}>{payables.paid} ₽</div></div>
        <div className="kpi"><div className="kpi__label">Остаток к оплате</div><div className="kpi__value" style={{ fontSize: 22, color: "var(--amber-600, #d97706)" }}>{payables.outstanding} ₽</div></div>
      </div>

      <Card title="Счета" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Документ</th>
                <th>Контрагент</th>
                <th style={{ textAlign: "right" }}>Сумма, ₽</th>
                <th style={{ textAlign: "right" }}>Оплачено, ₽</th>
                <th>Срок</th>
                <th>Статус</th>
                <th>Оплата</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((i) => (
                <tr key={i.id}>
                  <td className="table__muted">{i.id}</td>
                  <td className="table__strong">{i.number}</td>
                  <td>{i.counterparty}</td>
                  <td style={{ textAlign: "right" }} className="table__strong">{i.amount}</td>
                  <td style={{ textAlign: "right" }}>{i.paid}</td>
                  <td className="table__muted">{i.due}</td>
                  <td><Badge tone={i.statusTone}>{i.status}</Badge></td>
                  <td><Badge tone={i.paymentTone}>{i.paymentStatus}</Badge></td>
                  <td>
                    {i.status === "Черновик" ? (
                      <button className="btn btn--ghost btn--sm">Зарегистрировать</button>
                    ) : i.paymentStatus !== "Оплачен" ? (
                      <button className="btn btn--emerald btn--sm">Заявка на оплату</button>
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
          Счета (<strong>invoices</strong>) связываются с договором, обязательством и статьёй
          бюджета; файл счёта хранится через <strong>documents</strong>. Оплата счёта возможна
          только после регистрации и согласованной заявки. Система не проводит банковских
          операций — платёж фиксируется вручную.
        </div>
      </div>
    </>
  );
}
