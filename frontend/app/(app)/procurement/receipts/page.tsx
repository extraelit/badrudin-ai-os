/* Модуль «Снабжение и закупки». Экран 5 — поступление и входной контроль. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { receipts } from "../../../../lib/procurement";

export default function ReceiptsPage() {
  return (
    <>
      <PageHead
        title="Поступление и входной контроль"
        desc="Приёмка не больше заказа; проверка качества и сертификатов; оприходование на склад"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Оформить поступление</button>}
      />

      <Card title="Поступления" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Заказ</th>
                <th>Поставщик</th>
                <th>Принято</th>
                <th>Годно</th>
                <th>Брак</th>
                <th>Качество</th>
                <th>Сертификат</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {receipts.map((r) => (
                <tr key={r.id}>
                  <td className="table__muted">{r.id}</td>
                  <td>{r.order}</td>
                  <td className="table__strong">{r.supplier}</td>
                  <td>{r.received}</td>
                  <td>{r.accepted}</td>
                  <td style={r.rejected !== "0" ? { color: "var(--red-600)", fontWeight: 600 } : undefined}>{r.rejected}</td>
                  <td><Badge tone={r.qualityTone}>{r.quality}</Badge></td>
                  <td><Badge tone={r.certTone}>{r.cert}</Badge></td>
                  <td>
                    <button className="btn btn--emerald btn--sm">Оприходовать</button>
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
          Приёмка не может превышать заказанное количество. Сертификаты и накладные хранятся через
          документооборот (documents/document_versions/files). Оприходуется только принятое количество —
          проводка на склад идемпотентна.
        </div>
      </div>
    </>
  );
}
