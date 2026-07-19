/* Модуль «Ядро CRM». Экран 6 — договоры. */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { contracts } from "../../../../lib/crm";

export default function ContractsPage() {
  return (
    <>
      <PageHead
        title="Договоры"
        desc="Согласование R3 / крупный — R4 + MFA; подписанный договор — основание для проекта"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новый договор</button>}
      />

      <Card title="Договоры" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Номер</th>
                <th>Заказчик</th>
                <th>Предмет</th>
                <th>Сумма</th>
                <th>Подписан</th>
                <th>Риск</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((c) => (
                <tr key={c.id}>
                  <td className="table__muted">{c.id}</td>
                  <td className="table__strong">{c.number}</td>
                  <td>{c.client}</td>
                  <td>{c.subject}</td>
                  <td className="table__strong">{c.amount}</td>
                  <td className="table__muted">{c.signed}</td>
                  <td><Risk level={c.risk} /></td>
                  <td><Badge tone={c.statusTone}>{c.status}</Badge></td>
                  <td>
                    {c.status === "На согласовании" ? (
                      <button className="btn btn--emerald btn--sm">Утвердить</button>
                    ) : c.status === "Черновик" ? (
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
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Договоры (<strong>contracts</strong>) связывают заказчика, сделку, коммерческое
          предложение и проект. Утверждение/подписание проходит согласование человеком:
          <strong> R3</strong> — обычный, <strong> R4 + MFA</strong> — крупный (порог организации).
          Файл договора хранится через <strong>documents</strong>. Проект создаётся только по
          выигранной сделке и утверждённому/подписанному договору.
        </div>
      </div>
    </>
  );
}
