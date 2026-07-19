/* Модуль «Ядро CRM». Экран 7 — коммерческие предложения (переиспользование). */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { offers } from "../../../../lib/crm";

export default function CrmOffersPage() {
  return (
    <>
      <PageHead
        title="Коммерческие предложения"
        desc="Единая сущность commercial_offers сметного модуля; сделка ссылается на КП"
      />

      <Card title="КП по сделкам" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№ КП</th>
                <th>Сделка</th>
                <th>Заказчик</th>
                <th>Смета</th>
                <th>Наценка</th>
                <th>Цена заказчику</th>
                <th>Риск</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {offers.map((o) => (
                <tr key={o.id}>
                  <td className="table__muted">{o.id}</td>
                  <td className="table__muted">{o.deal}</td>
                  <td className="table__strong">{o.client}</td>
                  <td>{o.estimate}</td>
                  <td>{o.markup}</td>
                  <td className="table__strong">{o.offer}</td>
                  <td><Risk level={o.risk} /></td>
                  <td><Badge tone={o.statusTone}>{o.status}</Badge></td>
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
          Коммерческие предложения не дублируются: используется существующая сущность
          <strong> commercial_offers</strong> из модуля «Сметы и ценообразование». Сделка ссылается
          на КП (<strong>deal.commercial_offer_id</strong>). Наценка к утверждённой смете, итоговая
          цена и согласование (R3/R4 + MFA) остаются в сметном контуре — CRM показывает их в разрезе
          сделки без переноса логики.
        </div>
      </div>
    </>
  );
}
