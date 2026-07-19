"use client";

/* «KPI и независимый аудит» (backend /kpi). KPI — только для чтения из существующих
 * данных; находки аудита — отдельные записи, проверяемые данные не изменяются.
 * Данные из backend, без mock; без backend — честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { apiBaseConfigured } from "../../../lib/authApi";
import { kpiApi, type Finding, type KpiSummary } from "../../../lib/kpiApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  open: "amber", acknowledged: "navy", resolved: "emerald", false_positive: "gray",
};
const SEV: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  low: "gray", medium: "amber", high: "red",
};

export default function KpiPage() {
  const live = apiBaseConfigured();
  const [sum, setSum] = useState<KpiSummary | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("anomalous_expense");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    kpiApi.summary().then(setSum).catch(() => undefined);
    kpiApi.listFindings().then(setFindings).catch(() => undefined);
  };
  useEffect(() => { if (live) reload(); }, [live]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="KPI и независимый аудит" desc="Объективные показатели и находки аудита из данных системы" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="KPI и независимый аудит" desc="Показатели считаются из существующих данных; находки аудита — отдельные записи · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Задачи" value={String(sum?.tasks_total ?? "—")} icon="tasks" tone="navy" foot={`завершено: ${sum?.tasks_completed ?? 0}`} />
        <Kpi label="Просрочено" value={String(sum?.tasks_overdue ?? "—")} icon="approvals" tone={sum && sum.tasks_overdue ? "red" : "emerald"} foot={`доля: ${sum ? Math.round(sum.overdue_ratio * 100) : 0}%`} />
        <Kpi label="Открытые риски" value={String(sum?.risks_open ?? "—")} icon="approvals" tone={sum && sum.risks_high ? "amber" : "navy"} foot={`высоких: ${sum?.risks_high ?? 0}`} />
        <Kpi label="Находки аудита" value={String(sum?.findings_open ?? "—")} icon="reports" tone={sum && sum.findings_high ? "red" : "emerald"} foot={`высоких: ${sum?.findings_high ?? 0}`} />
      </div>

      <Card title="Независимый аудит — находки" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap", alignItems: "center" }}>
          <button className="btn btn--primary btn--sm" onClick={() => run(() => kpiApi.scan(), "Сканирование выполнено")}>Запустить сканирование</button>
          <span className="muted" style={{ fontSize: 12 }}>·</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)} style={sel}>
            {["anomalous_expense", "unusual_change", "bypassed_approval", "incomplete_log", "missing_evidence", "agent_quality", "other"].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input placeholder="Заголовок находки" value={title} onChange={(e) => setTitle(e.target.value)} style={inp} />
          <button className="btn btn--ghost btn--sm" onClick={() => { if (title) { run(() => kpiApi.createFinding({ category, title }), "Находка добавлена"); setTitle(""); } }}>Добавить вручную</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Категория</th><th>Важность</th><th>Заголовок</th><th>Источник</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {findings.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Находок нет.</td></tr>}
              {findings.map((f) => (
                <tr key={f.id}>
                  <td className="table__muted">{f.category}</td>
                  <td><Badge tone={SEV[f.severity] || "gray"}>{f.severity}</Badge></td>
                  <td className="table__strong">{f.title}</td>
                  <td>{f.detected_by === "scan" ? "сканирование" : "вручную"}</td>
                  <td><Badge tone={ST[f.status] || "gray"}>{f.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {(f.status === "open" || f.status === "acknowledged") && (
                      <>
                        <button className="btn btn--emerald btn--sm" onClick={() => run(() => kpiApi.resolve(f.id, "resolved", "разобрано"), "Находка закрыта")}>Закрыть</button>
                        <button className="btn btn--ghost btn--sm" onClick={() => run(() => kpiApi.resolve(f.id, "false_positive"), "Отмечено как ложное")}>Ложное</button>
                      </>
                    )}
                    {(f.status === "resolved" || f.status === "false_positive") && <span className="muted" style={{ fontSize: 12 }}>✓ разобрано</span>}
                  </td>
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
          KPI вычисляются <strong>только для чтения</strong> из существующих данных.
          Независимый аудит фиксирует находки как <strong>отдельные записи</strong> и
          <strong> не изменяет</strong> проверяемые данные (§20). Сканирование
          детерминированное и идемпотентное. Доступ: <strong>kpi.view</strong> /
          <strong> audit.finding.view</strong> / <strong>audit.finding.manage</strong> /
          <strong> audit.finding.resolve</strong>. Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 170, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
const sel: React.CSSProperties = { padding: "8px 10px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
