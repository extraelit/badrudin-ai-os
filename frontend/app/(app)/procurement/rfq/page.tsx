/* Модуль «Снабжение и закупки». Экран 3 — запросы цен и сравнение КП. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { rfqs, rfqOffers } from "../../../../lib/procurement";

export default function RfqPage() {
  return (
    <>
      <PageHead
        title="Запросы цен и сравнение КП"
        desc="Сбор предложений поставщиков и выбор согласованной цены (общий контур quote_comparisons)"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новый запрос цен</button>}
      />

      <Card title="Запросы цен" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Материал</th>
                <th>Поставщиков</th>
                <th>Предложений</th>
                <th>Лучшая цена</th>
                <th>Рекомендация</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {rfqs.map((r) => (
                <tr key={r.id}>
                  <td className="table__muted">{r.id}</td>
                  <td className="table__strong">{r.material}</td>
                  <td>{r.suppliers}</td>
                  <td>{r.offers}</td>
                  <td className="table__strong">{r.best}</td>
                  <td>{r.bestSupplier}</td>
                  <td><Badge tone={r.statusTone}>{r.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Сравнение предложений — Труба ПНД Ø315 (ЗЦ-711)" flush>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Поставщик</th><th>Цена</th><th>Срок</th><th>Выбор</th></tr>
            </thead>
            <tbody>
              {rfqOffers.map((o) => (
                <tr key={o.supplier} style={o.best ? { background: "var(--emerald-50)" } : undefined}>
                  <td className="table__strong">{o.supplier}</td>
                  <td>{o.price}</td>
                  <td>{o.lead}</td>
                  <td>{o.best ? <Badge tone="emerald">Рекомендовано</Badge> : <button className="btn btn--ghost btn--sm">Выбрать</button>}</td>
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
          Сравнение и выбор поставщика ведутся общей сущностью <strong>quote_comparisons</strong> (контур снабжения),
          без дублирования. Рекомендация ИИ не окончательна: выбор фиксируется с обоснованием и проходит согласование.
        </div>
      </div>
    </>
  );
}
