/* Модуль «Ядро CRM». Экран 2 — лиды и их обработка. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { leads } from "../../../../lib/crm";

export default function LeadsPage() {
  return (
    <>
      <PageHead
        title="Лиды"
        desc="Входящие обращения и источники; квалификация и конвертация в сделку"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новый лид</button>}
      />

      <Card title="Лиды" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Запрос</th>
                <th>Компания</th>
                <th>Источник</th>
                <th>Контакт</th>
                <th>Телефон</th>
                <th>Оценка</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id}>
                  <td className="table__muted">{l.id}</td>
                  <td className="table__strong">{l.title}</td>
                  <td>{l.company}</td>
                  <td><span className="badge badge--navy">{l.source}</span></td>
                  <td>{l.contact}</td>
                  <td className="table__muted">{l.phone}</td>
                  <td>{l.amount}</td>
                  <td><Badge tone={l.statusTone}>{l.status}</Badge></td>
                  <td>
                    {l.status === "Квалифицирован" ? (
                      <button className="btn btn--emerald btn--sm">В сделку</button>
                    ) : l.status === "Новый" ? (
                      <button className="btn btn--ghost btn--sm">Квалифицировать</button>
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
          Телефоны и e-mail лидов — персональные данные: показываются в маскированном виде,
          полный доступ — по праву <strong>crm.contact.pii</strong>. Квалифицированный лид
          конвертируется в сделку (<strong>lead → deal</strong>) без потери истории; источник
          фиксируется для аналитики (<strong>lead_sources</strong>).
        </div>
      </div>
    </>
  );
}
