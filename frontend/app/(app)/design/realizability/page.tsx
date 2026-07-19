/* Модуль «Проектирование и дизайн». Экран 7 — проверка реализуемости и поставщики. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { realizability, designSuppliers } from "../../../../lib/design";

export default function RealizabilityPage() {
  return (
    <>
      <PageHead
        title="Проверка реализуемости и поставщики"
        desc="Наличие, цены, сроки поставки и допустимые поставщики по проектным решениям"
        action={<button className="btn btn--ghost btn--sm">Обновить проверку</button>}
      />

      <Card title="Реализуемость проектных решений" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Позиция</th>
                <th>Наличие</th>
                <th>Поставщиков</th>
                <th>Цена (мин–макс)</th>
                <th>Срок</th>
                <th>Доставка в регион</th>
                <th>Рекомендация</th>
              </tr>
            </thead>
            <tbody>
              {realizability.map((r) => (
                <tr key={r.spec}>
                  <td className="table__strong">{r.spec}</td>
                  <td><Badge tone={r.availTone}>{r.availability}</Badge></td>
                  <td>{r.suppliers}</td>
                  <td>{r.minPrice} – {r.maxPrice}</td>
                  <td>{r.lead}</td>
                  <td>{r.region ? <Badge tone="emerald">Да</Badge> : <Badge tone="amber">Уточнить</Badge>}</td>
                  <td className="table__muted">{r.recommended}</td>
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
                <th>Категории</th>
                <th>Регион</th>
                <th>Срок</th>
                <th>Рейтинг</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {designSuppliers.map((s) => (
                <tr key={s.name}>
                  <td className="table__strong">{s.name}</td>
                  <td>{s.categories}</td>
                  <td>{s.region}</td>
                  <td>{s.lead}</td>
                  <td><span className="badge badge--amber">★ {s.rating}</span></td>
                  <td><Badge tone="emerald">{s.status}</Badge></td>
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
          Проверка реализуемости выполняется сервисом (рекомендация, R0/R1) на демонстрационных данных.
          Интерфейс готов к подключению реальных каталогов, цен, остатков и сроков поставщиков.
        </div>
      </div>
    </>
  );
}
