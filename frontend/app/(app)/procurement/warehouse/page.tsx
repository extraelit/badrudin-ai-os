/* Модуль «Снабжение и закупки». Экран 6 — склад: остатки и движения. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { balances, movements } from "../../../../lib/procurement";

export default function WarehousePage() {
  return (
    <>
      <PageHead
        title="Склад: остатки и движения"
        desc="Остатки, резервы, средняя себестоимость и журнал движений (проводок)"
        action={
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn--ghost btn--sm">Перемещение</button>
            <button className="btn btn--ghost btn--sm"><Icons.plus width={16} height={16} /> Списание</button>
          </div>
        }
      />

      <Card title="Остатки на складах" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Материал</th>
                <th>Склад</th>
                <th>Остаток</th>
                <th>Резерв</th>
                <th>Средняя себестоимость</th>
              </tr>
            </thead>
            <tbody>
              {balances.map((b) => (
                <tr key={b.material + b.warehouse}>
                  <td className="table__strong">{b.material}</td>
                  <td>{b.warehouse}</td>
                  <td className="table__strong">{b.qty}</td>
                  <td className="table__muted">{b.reserved}</td>
                  <td>{b.avgCost}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Журнал движений" flush>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Тип</th>
                <th>Материал</th>
                <th>Количество</th>
                <th>Склад</th>
                <th>Дата</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {movements.map((m) => (
                <tr key={m.id}>
                  <td className="table__muted">{m.id}</td>
                  <td><Badge tone={m.typeTone}>{m.type}</Badge></td>
                  <td className="table__strong">{m.material}</td>
                  <td>{m.qty}</td>
                  <td>{m.warehouse}</td>
                  <td>{m.date}</td>
                  <td><Badge tone={m.statusTone}>{m.status}</Badge></td>
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
          Каждое движение — идемпотентная проводка (inventory_transactions), меняющая остаток
          транзакционно; двойное проведение исключено. Списание требует согласования (R3/R4).
        </div>
      </div>
    </>
  );
}
