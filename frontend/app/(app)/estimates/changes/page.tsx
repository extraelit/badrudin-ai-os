/* Модуль «Сметы и ценообразование». Экран 7 — изменения сметы. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { changes } from "../../../../lib/estimates";

export default function ChangesPage() {
  return (
    <>
      <PageHead
        title="Изменения сметы"
        desc="Журнал причин изменения цены и объёма, версии и change order"
        action={<button className="btn btn--primary btn--sm">Оформить изменение</button>}
      />

      <Card title="Журнал изменений" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Тип</th>
                <th>Причина</th>
                <th>Влияние на стоимость</th>
                <th>Дата</th>
                <th>Автор</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {changes.map((c) => (
                <tr key={c.id}>
                  <td className="table__muted">{c.id}</td>
                  <td><span className="badge badge--navy">{c.type}</span></td>
                  <td className="table__strong">{c.reason}</td>
                  <td><Badge tone={c.deltaTone}>{c.delta}</Badge></td>
                  <td>{c.date}</td>
                  <td>{c.author}</td>
                  <td><Badge tone={c.statusTone}>{c.status}</Badge></td>
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
          <div className="table__strong">Утверждённую смету нельзя менять напрямую</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            Изменения вносятся только новой версией сметы или через change order с обязательной
            причиной. Прежняя утверждённая версия помечается «superseded». Все изменения цены и
            объёма фиксируются в этом журнале и в аудите.
          </div>
        </div>
      </div>
    </>
  );
}
