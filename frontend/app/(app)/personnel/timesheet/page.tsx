"use client";

/* Модуль «Персонал объектов». Экран 3 — табель рабочего времени. */
import { useState } from "react";
import { PageHead, Card, Badge } from "../../../../components/ui";
import { timesheet, timesheetTotals } from "../../../../lib/personnel";

export default function TimesheetPage() {
  const sites = ["Все объекты", ...Array.from(new Set(timesheet.map((t) => t.site)))];
  const [site, setSite] = useState("Все объекты");

  const rows = timesheet.filter((t) => site === "Все объекты" || t.site === site);

  return (
    <>
      <PageHead
        title="Табель рабочего времени"
        desc="Смены, часы, переработки, простои и отсутствия · период 01–18.07.2026"
        action={<button className="btn btn--ghost btn--sm">Экспорт табеля</button>}
      />

      <Card className="span-2" flush>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <div className="chips">
            {sites.map((s) => (
              <button key={s} className={`chip${site === s ? " chip--active" : ""}`} onClick={() => setSite(s)}>{s}</button>
            ))}
          </div>
          <div className="topbar__spacer" />
          <select className="chip" style={{ cursor: "pointer" }} defaultValue="Июль 2026">
            <option>Июль 2026</option>
            <option>Июнь 2026</option>
          </select>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Работник</th>
                <th>Бригада</th>
                <th>Объект</th>
                <th>День</th>
                <th>Смена</th>
                <th>Часы</th>
                <th>Переработка</th>
                <th>Простой</th>
                <th>Отсутствие</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t, i) => (
                <tr key={i}>
                  <td className="table__strong">{t.worker}</td>
                  <td>{t.brigade}</td>
                  <td>{t.site}</td>
                  <td>{t.day}</td>
                  <td>{t.shift}</td>
                  <td className="table__strong">{t.hours}</td>
                  <td style={t.overtime > 0 ? { color: "var(--amber-600)", fontWeight: 600 } : undefined}>{t.overtime || "—"}</td>
                  <td style={t.idle > 0 ? { color: "var(--amber-600)", fontWeight: 600 } : undefined}>{t.idle || "—"}</td>
                  <td>{t.absence === "—" ? <span className="muted">—</span> : <Badge tone={t.tone}>{t.absence}</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title={`Месячный итог — ${timesheetTotals.worker}`}>
        <div className="grid grid--kpi">
          <div><div className="kpi__label">Период</div><div className="table__strong" style={{ marginTop: 6 }}>{timesheetTotals.period}</div></div>
          <div><div className="kpi__label">Отработано дней</div><div className="kpi__value" style={{ fontSize: 24 }}>{timesheetTotals.daysWorked}</div></div>
          <div><div className="kpi__label">Часов / переработка</div><div className="kpi__value" style={{ fontSize: 24 }}>{timesheetTotals.hours} / {timesheetTotals.overtime}</div></div>
          <div><div className="kpi__label">Простои / отсутствия</div><div className="kpi__value" style={{ fontSize: 24 }}>{timesheetTotals.idle} / {timesheetTotals.absences}</div></div>
        </div>
      </Card>
    </>
  );
}
