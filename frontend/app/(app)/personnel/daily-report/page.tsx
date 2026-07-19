/* Модуль «Персонал объектов». Экран 8 — ежедневный отчёт прораба. */
import { PageHead, Card, Badge, Progress } from "../../../../components/ui";
import {
  dailyReport,
  dailyByProfession,
  dailyWorks,
  dailyEquipment,
  dailyIssues,
} from "../../../../lib/personnel";

export default function DailyReportPage() {
  const total = dailyByProfession.reduce((s, p) => s + p.count, 0);
  return (
    <>
      <PageHead
        title="Ежедневный отчёт прораба"
        desc={`${dailyReport.site} · ${dailyReport.date} · прораб ${dailyReport.foreman}`}
        action={
          <>
            <button className="btn btn--ghost btn--sm">Передать ПТО</button>
            <button className="btn btn--emerald btn--sm">Подтвердить отчёт</button>
          </>
        }
      />

      <div className="row row--between" style={{ marginBottom: 18 }}>
        <Badge tone={dailyReport.statusTone}>{dailyReport.status}</Badge>
        <span className="muted" style={{ fontSize: 13 }}>После подтверждения отчёт передаётся директору и в ПТО</span>
      </div>

      <div className="grid grid--3" style={{ marginBottom: 18 }}>
        <Card title={`Численность по профессиям — всего ${total}`}>
          <div className="stack" style={{ gap: 12 }}>
            {dailyByProfession.map((p) => (
              <div key={p.profession}>
                <div className="row row--between" style={{ marginBottom: 5 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{p.profession}</span>
                  <span className="muted">{p.count} чел.</span>
                </div>
                <div className="progress"><div className="progress__bar" style={{ width: `${(p.count / total) * 100}%` }} /></div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Выполненные работы и объёмы" className="span-2" flush>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Работа</th><th>Ед.</th><th>План</th><th>Факт</th><th>Выполнение</th></tr></thead>
              <tbody>
                {dailyWorks.map((w) => (
                  <tr key={w.work}>
                    <td className="table__strong">{w.work}</td>
                    <td>{w.unit}</td>
                    <td>{w.plan}</td>
                    <td>{w.fact}</td>
                    <td style={{ minWidth: 140 }}>
                      <Progress value={Math.round((w.fact / w.plan) * 100)} tone={w.fact < w.plan ? "amber" : undefined} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="grid grid--2" style={{ marginBottom: 18 }}>
        <Card title="Использованная техника" flush>
          <div className="list">
            {dailyEquipment.map((e) => (
              <div key={e.name} className="list__item">
                <div className="list__main"><div className="list__title">{e.name}</div></div>
                <Badge tone={e.tone}>{e.hours > 0 ? `${e.hours} ч` : "простой"}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Простои, материалы и происшествия" flush>
          <div className="list">
            {dailyIssues.map((it, i) => (
              <div key={i} className="list__item">
                <span className={`badge badge--${it.tone}`} style={{ minWidth: 84, justifyContent: "center" }}>{it.type}</span>
                <div className="list__sub" style={{ color: "var(--graphite-700)" }}>{it.text}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Фото до / после (демо)">
        <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
          {["До: траншея", "После: труба уложена", "До: основание", "После: бетон"].map((c) => (
            <div key={c} style={{ width: 170, height: 108, borderRadius: 10, background: "linear-gradient(135deg,var(--navy-100),var(--graphite-200))", display: "flex", alignItems: "flex-end", padding: 8, border: "1px solid var(--border)" }}>
              <span style={{ fontSize: 11, color: "var(--graphite-700)", background: "rgba(255,255,255,.85)", borderRadius: 5, padding: "2px 6px" }}>{c}</span>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
