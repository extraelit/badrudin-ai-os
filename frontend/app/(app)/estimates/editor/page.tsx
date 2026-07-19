/* Модуль «Сметы и ценообразование». Экран 2 — смета и позиции. */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { positions, estimateTotals, estimateGrand } from "../../../../lib/estimates";

export default function EstimateEditorPage() {
  return (
    <>
      <PageHead
        title="Локальная смета: сети ВК — v2"
        desc="Материалы, труд и машины · накладные, прибыль, НДС · статус: на проверке"
        action={
          <div className="row" style={{ gap: 8 }}>
            <Badge tone="amber">На проверке</Badge>
            <button className="btn btn--ghost btn--sm"><Icons.plus width={16} height={16} /> Позиция</button>
            <button className="btn btn--emerald btn--sm">Утвердить</button>
            <Risk level="R2" />
          </div>
        }
      />

      <Card title="Позиции сметы" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Расценка</th>
                <th>Наименование</th>
                <th>Ед.</th>
                <th>Кол-во</th>
                <th>Материалы</th>
                <th>Труд</th>
                <th>Машины</th>
                <th>НР</th>
                <th>СП</th>
                <th>Итого</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.no}>
                  <td className="table__muted">{p.no}</td>
                  <td className="table__muted">{p.code}</td>
                  <td className="table__strong">{p.name}</td>
                  <td>{p.unit}</td>
                  <td>{p.qty}</td>
                  <td>{p.material}</td>
                  <td>{p.labor}</td>
                  <td>{p.machine}</td>
                  <td>{p.overhead}</td>
                  <td>{p.profit}</td>
                  <td className="table__strong">{p.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="grid grid--3">
        <Card title="Свод по смете" className="span-2" flush>
          <div className="list">
            {estimateTotals.map((t) => (
              <div key={t.label} className="list__item">
                <div className="list__main"><div className="list__title" style={{ fontSize: 13 }}>{t.label}</div></div>
                <span className="table__strong">{t.value}</span>
              </div>
            ))}
            <div className="list__item" style={{ background: "var(--navy-50)" }}>
              <div className="list__main"><div className="list__title">Итого с НДС</div></div>
              <span className="table__strong" style={{ color: "var(--navy-700)", fontSize: 16 }}>{estimateGrand}</span>
            </div>
          </div>
        </Card>
        <Card title="Параметры расчёта">
          <div className="toggle"><span className="muted">Коэффициент индексации</span><span className="table__strong">1,00</span></div>
          <div className="toggle"><span className="muted">Накладные расходы</span><span className="table__strong">15%</span></div>
          <div className="toggle"><span className="muted">Сметная прибыль</span><span className="table__strong">8%</span></div>
          <div className="toggle"><span className="muted">НДС</span><span className="table__strong">20%</span></div>
          <div className="toggle"><span className="muted">Округление</span><span className="table__strong">0,01 ₽</span></div>
        </Card>
      </div>
    </>
  );
}
