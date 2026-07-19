/* Модуль «Сметы и ценообразование». Экран 4 — расценки и цены. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { rateItems } from "../../../../lib/estimates";

export default function RatesPage() {
  return (
    <>
      <PageHead
        title="Расценки и цены"
        desc="Справочник расценок (ручной ввод) и цены поставщиков из согласованных предложений"
        action={
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn--ghost btn--sm">Импорт (в разработке)</button>
            <button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Расценка</button>
          </div>
        }
      />

      <Card title="Справочник расценок" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Код</th>
                <th>Наименование</th>
                <th>Ед.</th>
                <th>Материалы</th>
                <th>Труд</th>
                <th>Машины</th>
                <th>Источник</th>
              </tr>
            </thead>
            <tbody>
              {rateItems.map((r) => (
                <tr key={r.code}>
                  <td className="table__muted">{r.code}</td>
                  <td className="table__strong">{r.name}</td>
                  <td>{r.unit}</td>
                  <td>{r.material}</td>
                  <td>{r.labor}</td>
                  <td>{r.machine}</td>
                  <td><Badge tone={r.sourceTone}>{r.source}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <div className="grid grid--2">
        <div className="alert">
          <div className="alert__icon">ℹ</div>
          <div className="muted" style={{ fontSize: 13 }}>
            В MVP расценки вводятся вручную. Заложен интерфейс адаптеров для будущего импорта
            ГЭСН/ФЕР/ТЕР; сами нормативные базы и файлы (.gsfx) хранятся как прикреплённые документы и версии.
          </div>
        </div>
        <div className="alert">
          <div className="alert__icon">🔗</div>
          <div className="muted" style={{ fontSize: 13 }}>
            Цены материалов берутся из каталога и товаров поставщиков; выбранные и согласованные
            цены поступают из общего контура снабжения (сравнение КП поставщиков) — без дублирования.
          </div>
        </div>
      </div>
    </>
  );
}
