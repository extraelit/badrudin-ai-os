"use client";

/* Задачи и поручения — рабочий контур (backend /core). Создание, отправка на
 * согласование, приёмка, ход исполнения и завершение. Согласование — на экране
 * «Согласования». */
import { useEffect, useState } from "react";
import { PageHead, Card, Badge, Risk } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured } from "../../../lib/authApi";
import { coreApi, type Project, type Task } from "../../../lib/coreApi";

const STATUS_TONE: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  draft: "gray", pending_approval: "amber", approved: "navy", assigned: "navy",
  accepted: "navy", in_progress: "navy", completed: "emerald", returned_for_revision: "red",
};

export default function TasksPage() {
  const live = apiBaseConfigured();
  const [projects, setProjects] = useState<Project[]>([]);
  const [sel, setSel] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => { if (live) coreApi.listProjects().then((p) => { setProjects(p); if (p[0]) setSel(p[0].id); }).catch(() => undefined); }, [live]);
  const reload = (pid: string) => coreApi.listTasks(pid).then(setTasks).catch(() => undefined);
  useEffect(() => { if (live && sel) reload(sel); }, [live, sel]);

  async function addTask() {
    if (!sel || !title.trim()) return;
    await coreApi.createTask(sel, { title: title.trim() });
    setTitle(""); reload(sel); setMsg("Поручение создано");
  }
  async function act(t: Task, action: "submit" | "accept" | "complete") {
    await coreApi.taskAction(t.id, action); reload(sel);
  }
  async function progress(t: Task) { await coreApi.taskProgress(t.id, 50); reload(sel); }

  if (!live) {
    return (
      <>
        <PageHead title="Задачи, сроки и просрочки" desc="Контроль исполнения поручений" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Задачи, сроки и просрочки"
        desc="Поручение → согласование → исполнение → завершение · данные из backend"
        action={
          <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)" }}>
            <option value="">— проект —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        }
      />
      {msg && <div className="alert" style={{ marginBottom: 16 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}

      {sel && (
        <Card title="Поручения проекта" flush className="span-2">
          <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
            <input placeholder="Что нужно сделать" value={title} onChange={(e) => setTitle(e.target.value)}
              style={{ flex: 1, minWidth: 220, padding: "8px 12px", border: "1px solid var(--line,#e2e8f0)", borderRadius: 8, fontSize: 14 }} />
            <button className="btn btn--primary btn--sm" onClick={addTask}><Icons.plus width={16} height={16} /> Создать поручение</button>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Поручение</th><th>Риск</th><th>Статус</th><th>Действие</th></tr></thead>
              <tbody>
                {tasks.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Поручений нет.</td></tr>}
                {tasks.map((t) => (
                  <tr key={t.id}>
                    <td className="table__strong">{t.title}</td>
                    <td><Risk level={t.risk_level as "R0" | "R1" | "R2" | "R3" | "R4"} /></td>
                    <td><Badge tone={STATUS_TONE[t.status] || "gray"}>{t.status}</Badge></td>
                    <td>
                      {t.status === "draft" && <button className="btn btn--ghost btn--sm" onClick={() => act(t, "submit")}>На согласование</button>}
                      {t.status === "approved" && <button className="btn btn--emerald btn--sm" onClick={() => act(t, "accept")}>Принять</button>}
                      {(t.status === "accepted") && <button className="btn btn--ghost btn--sm" onClick={() => progress(t)}>В работу</button>}
                      {(t.status === "in_progress") && <button className="btn btn--emerald btn--sm" onClick={() => act(t, "complete")}>Завершить</button>}
                      {t.status === "pending_approval" && <span className="muted" style={{ fontSize: 12 }}>ждёт согласования</span>}
                      {t.status === "completed" && <span className="muted" style={{ fontSize: 12 }}>✓ выполнено</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Каждое поручение проходит согласование руководителем (R2, экран «Согласования») перед
          исполнением. Все переходы фиксируются в журнале аудита на backend.
        </div>
      </div>
    </>
  );
}
