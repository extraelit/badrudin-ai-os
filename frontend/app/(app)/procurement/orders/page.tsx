/* Модуль «Снабжение и закупки». Экран 4 — заказы поставщикам. */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { orders } from "../../../../lib/procurement";

export default function OrdersPage() {
  return (
    <>
      <PageHead
        title="Заказы поставщикам"
        desc="Согласование заказа — R3 (крупный — R4 + MFA); при подтверждении резервируется остаток"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новый заказ</button>}
      />

      <Card title="Заказы" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Поставщик</th>
                <th>Позиции</th>
                <th>Сумма</th>
                <th>Поставка</th>
                <th>Риск</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td className="table__muted">{o.id}</td>
                  <td className="table__strong">{o.supplier}</td>
                  <td>{o.material}</td>
                  <td className="table__strong">{o.amount}</td>
                  <td>{o.eta}</td>
                  <td><Risk level={o.risk} /></td>
                  <td><Badge tone={o.statusTone}>{o.status}</Badge></td>
                  <td>
                    {o.status === "На согласовании" ? (
                      <div className="row" style={{ gap: 6 }}>
                        <button className="btn btn--emerald btn--sm">Согласовать</button>
                        <button className="btn btn--ghost btn--sm">Отклонить</button>
                      </div>
                    ) : o.status === "Черновик" ? (
                      <button className="btn btn--ghost btn--sm">На согласование</button>
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
      <div className="alert alert--danger">
        <div className="alert__icon">⚠</div>
        <div>
          <div className="table__strong">Согласование заказа — только человеком</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            Заказ уровня <strong>R3</strong> подтверждает уполномоченное лицо; уровня <strong>R4</strong>
            {" "}(крупная сумма) — с усиленной аутентификацией (MFA). Порог настраивается для организации.
            После подтверждения резервируется остаток под заказ. Все действия — в аудите.
          </div>
        </div>
      </div>
    </>
  );
}
