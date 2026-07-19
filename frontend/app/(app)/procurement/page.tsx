/* Экран 6. Снабжение и закупки. */
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { procurementKpis, purchases, suppliers } from "../../../lib/mock";

export default function ProcurementPage() {
  return (
    <>
      <PageHead
        title="Снабжение и закупки"
        desc="Заявки, поставки и база поставщиков по объектам"
        action={
          <button className="btn btn--primary btn--sm">
            <Icons.plus width={16} height={16} /> Новая заявка
          </button>
        }
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {procurementKpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <Card title="Заявки и поставки" more="Все заявки" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Материал</th>
                <th>Кол-во</th>
                <th>Объект</th>
                <th>Поставщик</th>
                <th>Сумма</th>
                <th>Поставка</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {purchases.map((p) => (
                <tr key={p.id}>
                  <td className="table__muted">{p.id}</td>
                  <td className="table__strong">{p.material}</td>
                  <td>{p.qty}</td>
                  <td>{p.site}</td>
                  <td>{p.supplier}</td>
                  <td className="table__strong">{p.sum}</td>
                  <td style={p.statusTone === "red" ? { color: "var(--red-600)", fontWeight: 600 } : undefined}>{p.eta}</td>
                  <td><Badge tone={p.statusTone}>{p.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Поставщики" flush>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Поставщик</th>
                <th>Категория</th>
                <th>Рейтинг</th>
                <th>Заказов</th>
                <th>В срок</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((s) => (
                <tr key={s.name}>
                  <td className="table__strong">{s.name}</td>
                  <td>{s.category}</td>
                  <td>
                    <span className="badge badge--amber">★ {s.rating}</span>
                  </td>
                  <td>{s.orders}</td>
                  <td>
                    <Badge tone={parseInt(s.onTime) >= 90 ? "emerald" : "amber"}>{s.onTime}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
