/* Экран 4. Согласования R0–R4. */
import { PageHead, Card, Badge, Risk } from "../../../components/ui";
import { approvals, riskScale } from "../../../lib/mock";

export default function ApprovalsPage() {
  return (
    <>
      <PageHead
        title="Согласования R0–R4"
        desc="Критические действия выполняются только после подтверждения человека (D-001, D-002)"
      />

      <Card title="Шкала риска действий" className="span-2">
        <div className="grid grid--3" style={{ gap: 12 }}>
          {riskScale.map((r) => (
            <div
              key={r.level}
              className="row"
              style={{ alignItems: "flex-start", gap: 10, padding: 10, border: "1px solid var(--border)", borderRadius: 10 }}
            >
              <Risk level={r.level} />
              <div>
                <div className="list__title" style={{ fontSize: 13 }}>{r.title}</div>
                <div className="muted" style={{ fontSize: 12 }}>{r.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Очередь согласований" more="История решений" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Предмет согласования</th>
                <th>Тип</th>
                <th>Сумма</th>
                <th>Инициатор</th>
                <th>Риск</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((a) => (
                <tr key={a.id}>
                  <td>
                    <div className="table__strong">{a.subject}</div>
                    <div className="table__muted">{a.id} · {a.date}</div>
                  </td>
                  <td>{a.type}</td>
                  <td className="table__strong">{a.amount ?? "—"}</td>
                  <td className="table__muted">{a.initiator}</td>
                  <td><Risk level={a.risk} /></td>
                  <td><Badge tone={a.statusTone}>{a.status}</Badge></td>
                  <td>
                    {a.status === "Ожидает" ? (
                      <div className="row" style={{ gap: 6 }}>
                        <button className="btn btn--emerald btn--sm">Согласовать</button>
                        <button className="btn btn--ghost btn--sm">Отклонить</button>
                      </div>
                    ) : (
                      <span className="muted" style={{ fontSize: 12 }}>Завершено</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="alert alert--danger">
        <div className="alert__icon">⚠</div>
        <div>
          <div className="table__strong">Действия уровня R4 требуют усиленной аутентификации</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            Согласование R4 (например, утверждение бюджета объекта) выполняется
            уполномоченным лицом с MFA и полной записью в журнал аудита. ИИ-агент
            только готовит проект решения.
          </div>
        </div>
      </div>
    </>
  );
}
