/* Модуль «Проектирование и дизайн». Экран 2 — ГИП: статус разделов. */
import { PageHead, Card, Badge, Progress, Risk } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { disciplines } from "../../../../lib/design";

export default function DisciplinesPage() {
  const issued = disciplines.filter((d) => d.status === "Выпущен").length;
  const checked = disciplines.filter((d) => d.gip === "Проверено").length;

  return (
    <>
      <PageHead
        title="ГИП — статус разделов проекта"
        desc="Комплектность, ответственные, сроки, готовность и проверка ГИП"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новый раздел</button>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Разделов</div><div className="kpi__value">{disciplines.length}</div></div>
        <div className="kpi"><div className="kpi__label">Проверено ГИП</div><div className="kpi__value" style={{ color: "var(--emerald-600)" }}>{checked}</div></div>
        <div className="kpi"><div className="kpi__label">Выпущено</div><div className="kpi__value" style={{ color: "var(--emerald-600)" }}>{issued}</div></div>
        <div className="kpi"><div className="kpi__label">Средняя готовность</div><div className="kpi__value">{Math.round(disciplines.reduce((s, d) => s + d.completion, 0) / disciplines.length)}%</div></div>
      </div>

      <Card title="Разделы и дисциплины" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Раздел</th>
                <th>Ответственный</th>
                <th>Срок</th>
                <th>Готовность</th>
                <th>Проверка ГИП</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {disciplines.map((d) => (
                <tr key={d.code}>
                  <td>
                    <div className="row" style={{ gap: 10 }}>
                      <span className="badge badge--navy" style={{ minWidth: 44, justifyContent: "center" }}>{d.code}</span>
                      <span className="table__strong">{d.name}</span>
                    </div>
                  </td>
                  <td>{d.responsible}</td>
                  <td>{d.due}</td>
                  <td style={{ minWidth: 150 }}><Progress value={d.completion} tone={d.completion < 50 ? "amber" : undefined} /></td>
                  <td><Badge tone={d.gipTone}>{d.gip}</Badge></td>
                  <td><Badge tone={d.statusTone}>{d.status}</Badge></td>
                  <td>
                    {d.status === "Выпущен" ? (
                      <span className="muted" style={{ fontSize: 12 }}>Выпущено</span>
                    ) : (
                      <div className="row" style={{ gap: 6 }}>
                        <button className="btn btn--emerald btn--sm">Выпустить</button>
                        <Risk level="R3" />
                      </div>
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
          <div className="table__strong">Выпуск и аннулирование документации</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            Выпуск раздела в производство возможен только через утверждённую версию документа и
            согласование <strong>R3</strong>. Аннулирование выпущенной документации — <strong>R4</strong>
            {" "}с подтверждением MFA. Все действия фиксируются в журнале аудита.
          </div>
        </div>
      </div>
    </>
  );
}
