/* Модуль «Снабжение и закупки». Экран 2 — заявки на материалы. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { requests } from "../../../../lib/procurement";

export default function RequestsPage() {
  return (
    <>
      <PageHead
        title="Заявки на материалы"
        desc="Проверка наличия позиции в смете и на складе; согласование заявки — R2"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новая заявка</button>}
      />

      <Card title="Заявки" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Объект</th>
                <th>Материал</th>
                <th>Кол-во</th>
                <th>Нужно к</th>
                <th>В смете</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id}>
                  <td className="table__muted">{r.id}</td>
                  <td>{r.site}</td>
                  <td className="table__strong">{r.material}</td>
                  <td>{r.qty}</td>
                  <td>{r.needed}</td>
                  <td>{r.inEstimate ? <Badge tone="emerald">Да</Badge> : <Badge tone="amber">Нет</Badge>}</td>
                  <td><Badge tone={r.statusTone}>{r.status}</Badge></td>
                  <td>
                    {r.status === "На согласовании" ? (
                      <button className="btn btn--emerald btn--sm">Утвердить</button>
                    ) : r.status === "Черновик" ? (
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
          Позиции заявки связаны со сметой (проверка «наличие в смете») и с проектом/объектом/зоной.
          Утверждённая заявка становится основанием для запроса цен и заказа. Все действия — в аудите.
        </div>
      </div>
    </>
  );
}
