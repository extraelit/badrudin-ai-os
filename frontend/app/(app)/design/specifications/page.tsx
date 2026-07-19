/* Модуль «Проектирование и дизайн». Экран 5 — спецификации / ведомости. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { specifications } from "../../../../lib/design";

export default function SpecificationsPage() {
  return (
    <>
      <PageHead
        title="Спецификации и ведомости"
        desc="Мебель, освещение, отделка и оборудование со связью с материалами и поставщиками"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Позиция</button>}
      />

      <div className="chips" style={{ marginBottom: 18 }}>
        <span className="chip chip--active">Все категории</span>
        <span className="chip">Отделка</span>
        <span className="chip">Освещение</span>
        <span className="chip">Мебель</span>
        <span className="chip">Оборудование</span>
      </div>

      <Card title="Ведомость спецификаций" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Категория</th>
                <th>Позиция</th>
                <th>Материал</th>
                <th>Поставщик</th>
                <th>Кол-во</th>
                <th>Цена</th>
                <th>Аналог</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {specifications.map((s) => (
                <tr key={s.name}>
                  <td><span className="badge badge--navy">{s.category}</span></td>
                  <td className="table__strong">{s.name}</td>
                  <td>{s.material}</td>
                  <td>{s.supplier}</td>
                  <td>{s.qty}</td>
                  <td className="table__strong">{s.price}</td>
                  <td>{s.analog ? <Badge tone="emerald">Разрешён</Badge> : <span className="muted">—</span>}</td>
                  <td><Badge tone={s.statusTone}>{s.status}</Badge></td>
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
          Спецификации ссылаются на каталог материалов и товары поставщиков (переиспользование, без
          дублирования). Замена на аналог допускается только с отметкой «аналог разрешён» и проверкой
          реализуемости.
        </div>
      </div>
    </>
  );
}
