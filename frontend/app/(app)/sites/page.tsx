/* Экран 2. Строительные объекты и проектные работы. */
import { PageHead, Card, Badge, Risk, Progress } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { sites, designWorks } from "../../../lib/mock";

export default function SitesPage() {
  return (
    <>
      <PageHead
        title="Строительные объекты и проектные работы"
        desc="Портфель из 8 объектов и 3 проектных работ"
        action={
          <button className="btn btn--primary btn--sm">
            <Icons.plus width={16} height={16} /> Новый объект
          </button>
        }
      />

      <div className="chips" style={{ marginBottom: 18 }}>
        <span className="chip chip--active">Все объекты</span>
        <span className="chip">В графике</span>
        <span className="chip">Отставание</span>
        <span className="chip">Завершение</span>
        <span className="chip">Проектные работы</span>
      </div>

      <Card title="Строительные объекты" more="Показать все" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Объект</th>
                <th>Заказчик</th>
                <th>Руководитель</th>
                <th>Готовность</th>
                <th>Бюджет / освоено</th>
                <th>Срок</th>
                <th>Статус</th>
                <th>Риск</th>
              </tr>
            </thead>
            <tbody>
              {sites.map((s) => (
                <tr key={s.id}>
                  <td>
                    <div className="table__strong">{s.name}</div>
                    <div className="table__muted">{s.id} · {s.address}</div>
                  </td>
                  <td>{s.customer}</td>
                  <td>{s.manager}</td>
                  <td style={{ minWidth: 150 }}>
                    <Progress
                      value={s.progress}
                      tone={s.statusTone === "amber" ? "amber" : undefined}
                    />
                  </td>
                  <td>
                    <div className="table__strong">{s.budgetM} млн ₽</div>
                    <div className="table__muted">освоено {s.spentM} млн ₽</div>
                  </td>
                  <td>{s.deadline}</td>
                  <td><Badge tone={s.statusTone}>{s.status}</Badge></td>
                  <td><Risk level={s.risk} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Проектно-изыскательские и дизайн-работы" flush>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Проектная работа</th>
                <th>Стадия</th>
                <th>ГИП / дизайнер</th>
                <th>Готовность</th>
                <th>Срок</th>
              </tr>
            </thead>
            <tbody>
              {designWorks.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div className="table__strong">{d.name}</div>
                    <div className="table__muted">{d.id}</div>
                  </td>
                  <td><Badge tone="navy">{d.stage}</Badge></td>
                  <td>{d.gip}</td>
                  <td style={{ minWidth: 150 }}><Progress value={d.progress} /></td>
                  <td>{d.deadline}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
