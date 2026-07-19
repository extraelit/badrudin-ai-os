/* Модуль «Снабжение и закупки». Экран 7 — выдача на объект и инвентаризация. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { issues, inventoryCount, countLines } from "../../../../lib/procurement";

export default function InventoryPage() {
  return (
    <>
      <PageHead
        title="Выдача на объект и инвентаризация"
        desc="Выдача материалов в производство (не больше остатка) и сверка фактических остатков"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Выдать на объект</button>}
      />

      <Card title="Выдача на объект" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Объект</th>
                <th>Материал</th>
                <th>Кол-во</th>
                <th>Кому</th>
                <th>Дата</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {issues.map((i) => (
                <tr key={i.id}>
                  <td className="table__muted">{i.id}</td>
                  <td>{i.site}</td>
                  <td className="table__strong">{i.material}</td>
                  <td>{i.qty}</td>
                  <td>{i.issuedTo}</td>
                  <td>{i.date}</td>
                  <td><Badge tone={i.statusTone}>{i.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card
        title={`Инвентаризация ${inventoryCount.number} · ${inventoryCount.warehouse}`}
        more={inventoryCount.status}
        flush
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Материал</th>
                <th>Ожидается</th>
                <th>Факт</th>
                <th>Расхождение</th>
              </tr>
            </thead>
            <tbody>
              {countLines.map((c) => (
                <tr key={c.material}>
                  <td className="table__strong">{c.material}</td>
                  <td>{c.expected}</td>
                  <td>{c.counted}</td>
                  <td><Badge tone={c.diffTone}>{c.diff}</Badge></td>
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
          Выдача не может превышать остаток на складе. Инвентаризация корректирует остаток на величину
          расхождения (проводка adjustment); все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}
