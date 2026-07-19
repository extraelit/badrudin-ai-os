/* Модуль «Ядро CRM». Экран 5 — единый центр коммуникаций. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { communications } from "../../../../lib/crm";

export default function CommunicationsPage() {
  return (
    <>
      <PageHead
        title="Центр коммуникаций"
        desc="Письма, звонки, встречи и сообщения; сообщение можно превратить в задачу"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Записать контакт</button>}
      />

      <Card title="История взаимодействий" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Канал</th>
                <th>Направление</th>
                <th>Тема</th>
                <th>Контрагент</th>
                <th>Когда</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {communications.map((c) => (
                <tr key={c.id}>
                  <td className="table__muted">{c.id}</td>
                  <td><Badge tone={c.channelTone}>{c.channel}</Badge></td>
                  <td>{c.direction}</td>
                  <td className="table__strong">{c.subject}</td>
                  <td>{c.counterparty}</td>
                  <td className="table__muted">{c.when}</td>
                  <td><Badge tone={c.statusTone}>{c.status}</Badge></td>
                  <td>
                    {c.status === "Новое" ? (
                      <button className="btn btn--ghost btn--sm">Создать задачу</button>
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
          Все каналы (e-mail, WhatsApp Business, Telegram, веб-форма, звонки, встречи) собираются
          в единую сущность <strong>communications</strong> с привязкой к контрагенту, лиду,
          сделке и проекту. Сообщение может порождать задачу (<strong>tasks</strong>) — без
          дублирования, через связь <strong>linked_task_id</strong>.
        </div>
      </div>
    </>
  );
}
