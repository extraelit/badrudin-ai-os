"use client";

/* Объекты и проекты — рабочий контур (backend /core). Создание проектов,
 * объектов и ежедневных отчётов; отправка отчёта на согласование. */
import { useEffect, useState } from "react";
import { PageHead, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured } from "../../../lib/authApi";
import { coreApi, type Project, type Site, type DailyReport } from "../../../lib/coreApi";

export default function SitesPage() {
  const live = apiBaseConfigured();
  const [projects, setProjects] = useState<Project[]>([]);
  const [sel, setSel] = useState<string>("");
  const [sites, setSites] = useState<Site[]>([]);
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [pname, setPname] = useState("");
  const [sname, setSname] = useState("");
  const [rsummary, setRsummary] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const loadProjects = () => coreApi.listProjects().then(setProjects).catch(() => setMsg("Ошибка загрузки проектов"));
  useEffect(() => { if (live) loadProjects(); }, [live]);
  useEffect(() => {
    if (!live || !sel) { setSites([]); setReports([]); return; }
    coreApi.listSites(sel).then(setSites).catch(() => undefined);
    coreApi.listReports(sel).then(setReports).catch(() => undefined);
  }, [live, sel]);

  async function addProject() {
    if (!pname.trim()) return;
    const p = await coreApi.createProject({ name: pname.trim() });
    setPname(""); await loadProjects(); setSel(p.id); setMsg("Проект создан");
  }
  async function addSite() {
    if (!sel || !sname.trim()) return;
    await coreApi.createSite(sel, { name: sname.trim() });
    setSname(""); coreApi.listSites(sel).then(setSites); setMsg("Объект создан");
  }
  async function addReport() {
    if (!sel) return;
    const r = await coreApi.createReport(sel, { report_date: new Date().toISOString().slice(0, 10), summary: rsummary || "Отчёт за день" });
    await coreApi.submitReport(r.id);
    setRsummary(""); coreApi.listReports(sel).then(setReports); setMsg("Отчёт отправлен на согласование");
  }

  if (!live) {
    return (
      <>
        <PageHead title="Строительные объекты и проектные работы" desc="Портфель проектов компании" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="Строительные объекты и проектные работы" desc="Проекты, объекты и ежедневные отчёты · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 16 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}

      <Card title="Проекты" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input className="input" placeholder="Название проекта" value={pname} onChange={(e) => setPname(e.target.value)} style={inp} />
          <button className="btn btn--primary btn--sm" onClick={addProject}><Icons.plus width={16} height={16} /> Создать проект</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Проект</th><th>Тип</th><th>Готовность</th><th>Статус</th><th></th></tr></thead>
            <tbody>
              {projects.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Проектов нет.</td></tr>}
              {projects.map((p) => (
                <tr key={p.id} style={p.id === sel ? { background: "var(--emerald-50)" } : undefined}>
                  <td className="table__strong">{p.name}</td>
                  <td className="table__muted">{p.project_type}</td>
                  <td>{p.completion_percent}%</td>
                  <td><Badge tone="emerald">{p.status}</Badge></td>
                  <td><button className="btn btn--ghost btn--sm" onClick={() => setSel(p.id)}>Открыть</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {sel && (
        <>
          <div style={{ height: 18 }} />
          <div className="grid grid--2">
            <Card title="Объекты проекта" flush>
              <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
                <input className="input" placeholder="Название объекта" value={sname} onChange={(e) => setSname(e.target.value)} style={inp} />
                <button className="btn btn--primary btn--sm" onClick={addSite}>Добавить</button>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Объект</th><th>Статус</th></tr></thead>
                  <tbody>
                    {sites.length === 0 && <tr><td colSpan={2} className="muted" style={{ padding: 16 }}>Объектов нет.</td></tr>}
                    {sites.map((s) => (<tr key={s.id}><td className="table__strong">{s.name}</td><td><Badge tone="emerald">{s.status}</Badge></td></tr>))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="Ежедневные отчёты" flush>
              <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
                <input className="input" placeholder="Кратко за день" value={rsummary} onChange={(e) => setRsummary(e.target.value)} style={inp} />
                <button className="btn btn--primary btn--sm" onClick={addReport}>Отчёт → на проверку</button>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Дата</th><th>Кратко</th><th>Статус</th></tr></thead>
                  <tbody>
                    {reports.length === 0 && <tr><td colSpan={3} className="muted" style={{ padding: 16 }}>Отчётов нет.</td></tr>}
                    {reports.map((r) => (<tr key={r.id}><td className="table__muted">{r.report_date}</td><td>{r.summary}</td><td><Badge tone={r.status === "approved" ? "emerald" : r.status === "submitted" ? "amber" : "gray"}>{r.status}</Badge></td></tr>))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      )}
    </>
  );
}

const inp: React.CSSProperties = {
  flex: 1, minWidth: 200, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)",
  borderRadius: 8, fontSize: 14,
};
