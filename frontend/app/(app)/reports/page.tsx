/* Экран 10. Отчёты и риски. */
import { PageHead, Kpi, Card, Badge, Donut } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { reportKpis, risks, reportsList } from "../../../lib/mock";

export default function ReportsPage() {
  return (
    <>
      <PageHead
        title="Отчёты и риски"
        desc="Аналитика по портфелю, ключевые показатели и реестр рисков"
        action={<button className="btn btn--ghost btn--sm">Сформировать отчёт</button>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {reportKpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <div className="grid grid--3" style={{ marginBottom: 18 }}>
        <Card title="Выполнение задач в срок">
          <div className="row" style={{ justifyContent: "center", padding: "8px 0" }}>
            <Donut value={83} caption="в срок" />
          </div>
        </Card>
        <Card title="Готовые отчёты" flush className="span-2">
          <div className="list">
            {reportsList.map((r) => (
              <div key={r.name} className="list__item">
                <div className="list__icon"><Icons.reports width={19} height={19} /></div>
                <div className="list__main">
                  <div className="list__title">{r.name}</div>
                  <div className="list__sub">{r.type} · период: {r.period}</div>
                </div>
                <button className="btn btn--ghost btn--sm">Открыть</button>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Реестр рисков" more="Матрица рисков" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Риск</th>
                <th>Категория</th>
                <th>Объект</th>
                <th>Уровень</th>
                <th>Ответственный</th>
                <th>Мера реагирования</th>
              </tr>
            </thead>
            <tbody>
              {risks.map((r) => (
                <tr key={r.title}>
                  <td className="table__strong">{r.title}</td>
                  <td>{r.category}</td>
                  <td>{r.site}</td>
                  <td><Badge tone={r.levelTone}>{r.level}</Badge></td>
                  <td>{r.owner}</td>
                  <td className="table__muted">{r.measure}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
