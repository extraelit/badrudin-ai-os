"use client";

/* «Реестр рисков» — рабочий контур (backend /risks). Идентификация, оценка
 * (вероятность × влияние → серьёзность), план снижения, принятие/закрытие.
 * Данные из backend, без mock; без backend — честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured } from "../../../lib/authApi";
import { coreApi, type Project } from "../../../lib/coreApi";
import { riskApi, type Risk, type RiskSummary } from "../../../lib/riskApi";

const SEV: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  low: "gray", medium: "navy", high: "amber", critical: "red",
};
const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  identified: "amber", assessed: "navy", mitigating: "navy", accepted: "emerald",
  closed: "emerald", realized: "red",
};
const CATS = ["schedule", "cost", "quality", "safety", "supply", "legal", "hr", "financial", "other"];
const LV = ["low", "medium", "high"];

export default function RisksPage() {
  const live = apiBaseConfigured();
  const [sum, setSum] = useState<RiskSummary | null>(null);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("other");
  const [prob, setProb] = useState("medium");
  const [impact, setImpact] = useState("medium");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    riskApi.summary().then(setSum).catch(() => undefined);
    riskApi.list().then(setRisks).catch(() => undefined);
  };
  useEffect(() => {
    if (!live) return;
    coreApi.listProjects().then((p) => { setProjects(p); if (p[0]) setProjectId(p[0].id); }).catch(() => undefined);
    reload();
  }, [live]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Реестр рисков" desc="Идентификация, оценка, снижение и принятие рисков" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Реестр рисков"
        desc="Вероятность × влияние → серьёзность; снижение и принятие — решение человека · данные из backend"
        action={
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} style={sel}>
            <option value="">— проект —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        }
      />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Открытые риски" value={String(sum?.open ?? "—")} icon="approvals" tone={sum && sum.open ? "amber" : "emerald"} foot={`всего: ${sum?.total ?? 0}`} />
        <Kpi label="Критические" value={String(sum?.critical ?? "—")} icon="reports" tone={sum && sum.critical ? "red" : "emerald"} foot="требуют решения" />
        <Kpi label="Высокие" value={String(sum?.high ?? "—")} icon="documents" tone={sum && sum.high ? "amber" : "emerald"} foot="под контролем" />
        <Kpi label="Реализовались" value={String(sum?.realized ?? "—")} icon="finance" tone={sum && sum.realized ? "red" : "emerald"} foot={`принято: ${sum?.accepted ?? 0}`} />
      </div>

      <Card title="Новый риск" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap", alignItems: "center" }}>
          <input placeholder="Описание риска" value={title} onChange={(e) => setTitle(e.target.value)} style={inp} />
          <select value={category} onChange={(e) => setCategory(e.target.value)} style={sel}>{CATS.map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <label style={{ fontSize: 12 }} className="muted">вер.</label>
          <select value={prob} onChange={(e) => setProb(e.target.value)} style={sel}>{LV.map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <label style={{ fontSize: 12 }} className="muted">влиян.</label>
          <select value={impact} onChange={(e) => setImpact(e.target.value)} style={sel}>{LV.map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <button className="btn btn--primary btn--sm" onClick={() => { if (title) { run(() => riskApi.register({ title, category, probability: prob, impact, project_id: projectId || undefined }), "Риск зарегистрирован"); setTitle(""); } }}><Icons.plus width={16} height={16} /> В реестр</button>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Реестр рисков" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Риск</th><th>Категория</th><th>Серьёзность</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {risks.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Рисков нет.</td></tr>}
              {risks.map((r) => (
                <tr key={r.id}>
                  <td className="table__strong">{r.title}</td>
                  <td className="table__muted">{r.category}</td>
                  <td><Badge tone={SEV[r.severity] || "gray"}>{r.severity}</Badge></td>
                  <td><Badge tone={ST[r.status] || "gray"}>{r.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {!["closed", "realized"].includes(r.status) && (
                      <>
                        <button className="btn btn--ghost btn--sm" onClick={() => { const p = prompt("План снижения:"); if (p) run(() => riskApi.mitigation(r.id, p), "План сохранён"); }}>План</button>
                        <button className="btn btn--emerald btn--sm" onClick={() => run(() => riskApi.decide(r.id, "accepted"), "Риск принят")}>Принять</button>
                        <button className="btn btn--ghost btn--sm" onClick={() => run(() => riskApi.decide(r.id, "closed"), "Риск закрыт")}>Закрыть</button>
                      </>
                    )}
                    {["closed", "realized"].includes(r.status) && <span className="muted" style={{ fontSize: 12 }}>✓ {r.status}</span>}
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
          Серьёзность вычисляется из матрицы «вероятность × влияние». Принятие, закрытие и фиксация
          реализации риска — решение человека (право <strong>risk.approve</strong>); регистрация и
          оценка — <strong>risk.manage</strong>; просмотр — <strong>risk.view</strong>. Риски с
          проектом ограничены доступом к проекту. Риск может порождаться из входящего обращения или
          задачи. Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 180, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
const sel: React.CSSProperties = { padding: "8px 10px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
