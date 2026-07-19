/* Модуль «Проектирование и дизайн». Экран 6 — реестр замечаний (→ задачи). */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { designIssues } from "../../../../lib/design";

export default function DesignIssuesPage() {
  const open = designIssues.filter((i) => i.status !== "Решено").length;
  const critical = designIssues.filter((i) => i.severity === "Критическое").length;

  return (
    <>
      <PageHead
        title="Реестр замечаний"
        desc="Замечания заказчика, экспертизы и нормоконтроля — автоматически становятся задачами"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Замечание</button>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Всего замечаний</div><div className="kpi__value">{designIssues.length}</div></div>
        <div className="kpi"><div className="kpi__label">Открытых</div><div className="kpi__value" style={{ color: "var(--amber-600)" }}>{open}</div></div>
        <div className="kpi"><div className="kpi__label">Критических</div><div className="kpi__value" style={{ color: "var(--red-600)" }}>{critical}</div></div>
        <div className="kpi"><div className="kpi__label">Связано с задачами</div><div className="kpi__value">{designIssues.length}</div></div>
      </div>

      <Card title="Замечания" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Замечание</th>
                <th>Источник</th>
                <th>Важность</th>
                <th>Ответственный</th>
                <th>Срок</th>
                <th>Задача</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {designIssues.map((i) => (
                <tr key={i.id}>
                  <td className="table__muted">{i.id}</td>
                  <td className="table__strong">{i.title}</td>
                  <td>{i.source}</td>
                  <td><Badge tone={i.severityTone}>{i.severity}</Badge></td>
                  <td>{i.responsible}</td>
                  <td style={i.status !== "Решено" ? { fontWeight: 600 } : undefined}>{i.due}</td>
                  <td><span className="badge badge--navy"><Icons.tasks width={12} height={12} /> {i.task}</span></td>
                  <td><Badge tone={i.statusTone}>{i.status}</Badge></td>
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
          Каждое замечание создаёт связанную задачу (tasks) с ответственным и сроком — без дублирования.
          Повторная приёмка выполняется после устранения; история сохраняется в аудите.
        </div>
      </div>
    </>
  );
}
