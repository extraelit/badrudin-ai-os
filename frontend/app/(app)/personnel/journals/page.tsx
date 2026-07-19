/* Модуль «Персонал объектов». Экран 6 — журналы прораба. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { journals } from "../../../../lib/personnel";

export default function JournalsPage() {
  const counts = {
    filled: journals.filter((j) => j.status === "Заполнен").length,
    check: journals.filter((j) => j.status === "Требует проверки").length,
    empty: journals.filter((j) => j.status === "Не заполнен").length,
    overdue: journals.filter((j) => j.status === "Просрочен").length,
  };

  return (
    <>
      <PageHead
        title="Журналы прораба"
        desc="Обязательные журналы работ и их состояние по объектам"
        action={<button className="btn btn--primary btn--sm">Проверить журналы</button>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Заполнены</div><div className="kpi__value" style={{ color: "var(--emerald-600)" }}>{counts.filled}</div><div className="kpi__icon kpi__icon--emerald"><Icons.documents width={22} height={22} /></div></div>
        <div className="kpi"><div className="kpi__label">Требуют проверки</div><div className="kpi__value" style={{ color: "var(--amber-600)" }}>{counts.check}</div><div className="kpi__icon kpi__icon--amber"><Icons.clock width={22} height={22} /></div></div>
        <div className="kpi"><div className="kpi__label">Не заполнены</div><div className="kpi__value" style={{ color: "var(--red-600)" }}>{counts.empty}</div><div className="kpi__icon kpi__icon--red"><Icons.alert width={22} height={22} /></div></div>
        <div className="kpi"><div className="kpi__label">Просрочены</div><div className="kpi__value" style={{ color: "var(--red-600)" }}>{counts.overdue}</div><div className="kpi__icon kpi__icon--red"><Icons.alert width={22} height={22} /></div></div>
      </div>

      <Card title="Реестр обязательных журналов" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Журнал</th>
                <th>Объект</th>
                <th>Ответственный</th>
                <th>Срок</th>
                <th>Вложения</th>
                <th>Состояние</th>
              </tr>
            </thead>
            <tbody>
              {journals.map((j) => (
                <tr key={j.name + j.site}>
                  <td>
                    <div className="row" style={{ gap: 10 }}>
                      <span className="list__icon" style={{ width: 32, height: 32 }}><Icons.documents width={16} height={16} /></span>
                      <span className="table__strong">{j.name}</span>
                    </div>
                  </td>
                  <td>{j.site}</td>
                  <td>{j.responsible}</td>
                  <td style={j.status === "Просрочен" ? { color: "var(--red-600)", fontWeight: 600 } : undefined}>{j.due}</td>
                  <td><span className="badge badge--gray">{j.attachments} 📎</span></td>
                  <td><Badge tone={j.statusTone}>{j.status}</Badge></td>
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
          Журналы переиспользуют документооборот (<strong>documents / document_versions</strong>) и связаны с
          объектом, ответственным и прикреплёнными фото. Все изменения фиксируются в журнале аудита.
        </div>
      </div>
    </>
  );
}
