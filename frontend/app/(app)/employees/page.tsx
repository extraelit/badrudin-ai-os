/* Экран 8. Сотрудники и структура организации. */
import { PageHead, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { employees, orgStructure } from "../../../lib/mock";

export default function EmployeesPage() {
  return (
    <>
      <PageHead
        title="Сотрудники и структура организации"
        desc="Кадры, роли и подразделения ООО «Экстра-Элит»"
        action={
          <button className="btn btn--primary btn--sm">
            <Icons.plus width={16} height={16} /> Добавить сотрудника
          </button>
        }
      />

      <div className="grid grid--3" style={{ marginBottom: 18 }}>
        <Card title="Подразделения" flush className="span-2">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Подразделение</th>
                  <th>Руководитель</th>
                  <th>Сотрудников</th>
                </tr>
              </thead>
              <tbody>
                {orgStructure.map((o) => (
                  <tr key={o.dept}>
                    <td className="table__strong">{o.dept}</td>
                    <td>{o.head}</td>
                    <td><span className="badge badge--navy">{o.people}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Всего в компании">
          <div style={{ textAlign: "center", padding: "10px 0" }}>
            <div className="kpi__value" style={{ fontSize: 40 }}>35</div>
            <div className="muted">сотрудников в 6 подразделениях</div>
            <div className="divider" style={{ margin: "16px 0" }} />
            <div className="row row--between" style={{ fontSize: 13, marginBottom: 8 }}>
              <span className="muted">На объектах</span><span className="table__strong">12</span>
            </div>
            <div className="row row--between" style={{ fontSize: 13, marginBottom: 8 }}>
              <span className="muted">В офисе</span><span className="table__strong">20</span>
            </div>
            <div className="row row--between" style={{ fontSize: 13 }}>
              <span className="muted">В отпуске</span><span className="table__strong">3</span>
            </div>
          </div>
        </Card>
      </div>

      <Card title="Сотрудники" more="Все сотрудники" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Сотрудник</th>
                <th>Должность</th>
                <th>Подразделение</th>
                <th>Проектов</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((e) => (
                <tr key={e.name}>
                  <td>
                    <div className="row" style={{ gap: 10 }}>
                      <span className="avatar-sm">{e.initials}</span>
                      <span className="table__strong">{e.name}</span>
                    </div>
                  </td>
                  <td>{e.position}</td>
                  <td>{e.dept}</td>
                  <td>{e.projects}</td>
                  <td><Badge tone={e.statusTone}>{e.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
