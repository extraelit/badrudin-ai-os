/* Экран 9. ИИ-агенты и их статусы. */
import { PageHead, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { agents, agentModes } from "../../../lib/mock";

export default function AgentsPage() {
  const active = agents.filter((a) => a.status === "Активен").length;

  return (
    <>
      <PageHead
        title="ИИ-агенты и их статусы"
        desc="Каждый агент действует строго в пределах роли; критические действия — через человека"
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Всего агентов</div>
          <div className="kpi__value">{agents.length}</div>
          <div className="kpi__icon kpi__icon--navy"><Icons.agents width={22} height={22} /></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Активны</div>
          <div className="kpi__value" style={{ color: "var(--emerald-600)" }}>{active}</div>
          <div className="kpi__icon kpi__icon--emerald"><Icons.agents width={22} height={22} /></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Запусков за сутки</div>
          <div className="kpi__value">780</div>
          <div className="kpi__icon kpi__icon--navy"><Icons.reports width={22} height={22} /></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Эскалаций</div>
          <div className="kpi__value" style={{ color: "var(--amber-600)" }}>4</div>
          <div className="kpi__icon kpi__icon--amber"><Icons.alert width={22} height={22} /></div>
        </div>
      </div>

      <div className="grid grid--3" style={{ marginBottom: 18 }}>
        {agents.map((a) => (
          <div key={a.name} className="card">
            <div className="card__body">
              <div className="row row--between" style={{ marginBottom: 10 }}>
                <span className="list__icon" style={{ background: "var(--navy-50)" }}>
                  <Icons.agents width={20} height={20} />
                </span>
                <Badge tone={a.statusTone}>{a.status}</Badge>
              </div>
              <div className="list__title">{a.name}</div>
              <div className="list__sub" style={{ marginBottom: 12 }}>{a.role}</div>
              <div className="divider" />
              <div className="row row--between" style={{ fontSize: 12.5, marginTop: 10 }}>
                <span className="muted">Режим</span>
                <span style={{ fontWeight: 600, textAlign: "right", maxWidth: 160 }}>{a.mode}</span>
              </div>
              <div className="row row--between" style={{ fontSize: 12.5, marginTop: 6 }}>
                <span className="muted">Запусков</span>
                <span style={{ fontWeight: 600 }}>{a.runs}</span>
              </div>
              <div className="row row--between" style={{ fontSize: 12.5, marginTop: 6 }}>
                <span className="muted">Последний запуск</span>
                <span style={{ fontWeight: 600 }}>{a.lastRun}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <Card title="Режимы работы агентов (MASTER_SPECIFICATION.md, раздел 3.2)">
        <div className="grid grid--3" style={{ gap: 12 }}>
          {agentModes.map((m, i) => (
            <div key={m} className="row" style={{ gap: 10, padding: 12, border: "1px solid var(--border)", borderRadius: 10 }}>
              <span className="risk risk--r2">{i + 1}</span>
              <span style={{ fontSize: 13, fontWeight: 500 }}>{m}</span>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
