"use client";

/* «Единый входящий поток» — рабочий контур (backend /inbox). Приём обращений,
 * классификация, назначение, конверсия в задачу, отклонение. Данные из backend,
 * без mock; без backend — честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured, me } from "../../../lib/authApi";
import { coreApi, type Project } from "../../../lib/coreApi";
import { inboxApi, type InboxItem, type InboxSummary } from "../../../lib/inboxApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  new: "amber", classified: "navy", in_progress: "navy", converted: "emerald", dismissed: "gray",
};
const CATS = ["request", "complaint", "inquiry", "document", "risk", "lead", "invoice", "other"];

export default function InboxPage() {
  const live = apiBaseConfigured();
  const [sum, setSum] = useState<InboxSummary | null>(null);
  const [items, setItems] = useState<InboxItem[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [empId, setEmpId] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    inboxApi.summary().then(setSum).catch(() => undefined);
    inboxApi.list().then(setItems).catch(() => undefined);
  };
  useEffect(() => {
    if (!live) return;
    me().then((u) => setEmpId(u.employee_id)).catch(() => undefined);
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
        <PageHead title="Единый входящий поток" desc="Приём, классификация и маршрутизация обращений" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Единый входящий поток"
        desc="Приём обращений → классификация → задача/документ/риск · данные из backend"
        action={
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} style={sel}>
            <option value="">— проект для маршрутизации —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        }
      />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Новые" value={String(sum?.new ?? "—")} icon="documents" tone={sum && sum.new ? "amber" : "emerald"} foot="без разбора" />
        <Kpi label="В работе" value={String((sum?.classified ?? 0) + (sum?.in_progress ?? 0))} icon="tasks" tone="navy" foot="классифицированы" />
        <Kpi label="Не разобрано" value={String(sum?.unresolved ?? "—")} icon="approvals" tone={sum && sum.unresolved ? "amber" : "emerald"} foot="требуют действия" />
        <Kpi label="Обработано" value={String(sum?.converted ?? "—")} icon="reports" tone="emerald" foot={`отклонено: ${sum?.dismissed ?? 0}`} />
      </div>

      <Card title="Новое обращение (ручной приём)" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Тема обращения" value={subject} onChange={(e) => setSubject(e.target.value)} style={inp} />
          <input placeholder="Кратко суть" value={body} onChange={(e) => setBody(e.target.value)} style={inp} />
          <button className="btn btn--primary btn--sm" onClick={() => { if (subject) { run(() => inboxApi.capture({ subject, body_text: body, channel: "manual" }), "Обращение принято"); setSubject(""); setBody(""); } }}><Icons.plus width={16} height={16} /> Принять</button>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Очередь входящих" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Тема</th><th>Канал</th><th>Категория</th><th>Приоритет</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Входящих обращений нет.</td></tr>}
              {items.map((i) => (
                <tr key={i.id}>
                  <td className="table__strong">{i.subject || "—"}</td>
                  <td className="table__muted">{i.channel}</td>
                  <td>{i.category ? <Badge tone="navy">{i.category}</Badge> : "—"}</td>
                  <td>{i.priority}</td>
                  <td><Badge tone={ST[i.status] || "gray"}>{i.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {["new", "classified", "in_progress"].includes(i.status) && (
                      <>
                        <select defaultValue="" onChange={(e) => { if (e.target.value) run(() => inboxApi.classify(i.id, { category: e.target.value, project_id: projectId || undefined, assigned_to_employee_id: empId || undefined }), "Классифицировано"); }} style={{ ...sel, padding: "4px 8px" }}>
                          <option value="">классифицировать…</option>
                          {CATS.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                        {i.project_id && <button className="btn btn--emerald btn--sm" onClick={() => run(() => inboxApi.convertToTask(i.id, { title: i.subject || undefined }), "Создано поручение")}>→ Задача</button>}
                        <button className="btn btn--ghost btn--sm" onClick={() => { const r = prompt("Причина отклонения:"); if (r) run(() => inboxApi.dismiss(i.id, r), "Отклонено"); }}>Отклонить</button>
                      </>
                    )}
                    {i.status === "converted" && <span className="muted" style={{ fontSize: 12 }}>→ {i.converted_entity_type}</span>}
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
          Единая очередь входящих обращений из разрешённых источников превращается в задачи, документы,
          заявки или риски — без дублирования сущностей (задача создаётся общим сервисом, связь по
          идентификатору). Внешние коннекторы (почта, официальные мессенджеры) подключаются отдельно и
          требуют настройки доступа. Доступ: <strong>inbox.view</strong> (очередь) и
          <strong> inbox.manage</strong> (разбор); обращения с проектом ограничены доступом к проекту.
          Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 180, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
const sel: React.CSSProperties = { padding: "8px 12px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
