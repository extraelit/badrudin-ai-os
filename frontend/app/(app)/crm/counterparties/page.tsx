/* Модуль «Ядро CRM». Экран 4 — заказчики и карточка контактов. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { counterparties, contacts } from "../../../../lib/crm";

export default function CounterpartiesPage() {
  return (
    <>
      <PageHead
        title="Заказчики и контакты"
        desc="Карточки клиентов (counterparties) и контактные лица с учётом согласий"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новый заказчик</button>}
      />

      <Card title="Заказчики" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Наименование</th>
                <th>ИНН</th>
                <th>Тип</th>
                <th>Сделок</th>
                <th>Сумма</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {counterparties.map((c) => (
                <tr key={c.id}>
                  <td className="table__muted">{c.id}</td>
                  <td className="table__strong">{c.name}</td>
                  <td className="table__muted">{c.inn}</td>
                  <td><span className="badge badge--navy">{c.type}</span></td>
                  <td>{c.deals}</td>
                  <td className="table__strong">{c.amount}</td>
                  <td><Badge tone={c.statusTone}>{c.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Карточка заказчика — ООО «СтройИнвест» · контактные лица" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>ФИО</th>
                <th>Должность</th>
                <th>E-mail</th>
                <th>Телефон</th>
                <th>Согласие на ПДн</th>
                <th>Основной</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((p) => (
                <tr key={p.name}>
                  <td className="table__strong">{p.name}</td>
                  <td>{p.position}</td>
                  <td className="table__muted">{p.email}</td>
                  <td className="table__muted">{p.phone}</td>
                  <td>{p.consent ? <Badge tone="emerald">Есть</Badge> : <Badge tone="red">Нет</Badge>}</td>
                  <td>{p.primary ? <Badge tone="navy">Основной</Badge> : <span className="muted">—</span>}</td>
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
          Контактные лица (<strong>counterparty_contacts</strong>) хранят согласие на обработку
          ПДн и его дату. Телефоны и e-mail показаны в маскированном виде — полный доступ только
          по праву <strong>crm.contact.pii</strong>. Заказчик связывается с проектом через
          формализованный ключ <strong>projects.customer_id</strong>.
        </div>
      </div>
    </>
  );
}
