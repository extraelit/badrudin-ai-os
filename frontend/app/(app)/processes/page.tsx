"use client";

/* «Процессы» — единое процессное ядро (backend /processes). Создание процесса,
 * назначение исполнителя и срока, принятие в работу, старт, отправка на проверку,
 * возврат на доработку и закрытие ТОЛЬКО проверяющим. Действия скрыты по правам
 * пользователя (сервер всё равно проверяет). Данные из backend; без backend —
 * честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Card, Badge } from "../../../components/ui";
import { apiBaseConfigured, me } from "../../../lib/authApi";
import { processApi, type WorkflowProcess } from "../../../lib/processApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  draft: "gray", pending_approval: "amber", approved: "navy", assigned: "navy",
  accepted: "navy", in_progress: "navy", submitted_for_review: "amber",
  revision_required: "red", completed: "emerald", archived: "gray",
  cancelled: "gray", rejected: "red", blocked: "red",
};
const KINDS = [
  "task", "construction", "construction_control", "acceptance_control",
  "incoming_control", "finance_payment", "defect", "daily_report",
];

export default function ProcessesPage() {
  const live = apiBaseConfigured();
  const [perms, setPerms] = useState<string[]>([]);
  const [items, setItems] = useState<WorkflowProcess[]>([]);
  const [kind, setKind] = useState("task");
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [execId, setExecId] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const has = (p: string) => perms.includes("system_owner") || perms.includes(p);
  const reload = () => processApi.list().then(setItems).catch(() => undefined);

  useEffect(() => {
    if (!live) return;
    me().then((u) => setPerms(u.permissions)).catch(() => undefined);
    reload();
  }, [live]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  async function create() {
    if (!title.trim()) return;
    await run(
      () => processApi.create({ process_kind: kind, title, due_at: dueAt || undefined }),
      "Процесс создан",
    );
    setTitle(""); setDueAt("");
  }

  if (!live) {
    return (
      <>
        <PageHead title="Процессы" desc="Единое процессное ядро" />
        <Card title="Backend не настроен">
          <p className="muted">Экран работает при подключённом backend (NEXT_PUBLIC_API_BASE_URL).</p>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Процессы"
        desc="Назначение исполнителя и срока, принятие в работу, отправка на проверку, возврат и закрытие проверяющим"
      />

      {(msg || err) && (
        <div className="alert" style={{ marginBottom: 14 }}>
          <div className="alert__icon">{err ? "⚠" : "✓"}</div>
          <div className="muted" style={{ fontSize: 13 }}>{err || msg}</div>
        </div>
      )}

      {has("task.create") && (
        <Card title="Новый процесс" flush>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: 14, alignItems: "center" }}>
            <select value={kind} onChange={(e) => setKind(e.target.value)} className="input">
              {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
            <input className="input" placeholder="Название процесса" value={title}
                   onChange={(e) => setTitle(e.target.value)} style={{ minWidth: 240 }} />
            <input className="input" type="datetime-local" value={dueAt}
                   onChange={(e) => setDueAt(e.target.value)} />
            <button className="btn btn--primary btn--sm" onClick={create}>Создать</button>
          </div>
        </Card>
      )}

      <div style={{ height: 14 }} />

      <Card title={`Процессы — ${items.length}`} flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Процесс</th><th>Вид</th><th>Риск</th><th>Статус</th>
                <th>Срок</th><th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id}>
                  <td className="table__strong">{p.title}</td>
                  <td className="muted">{p.process_kind}</td>
                  <td><Badge tone={p.risk_level === "R4" || p.risk_level === "R3" ? "red" : "navy"}>{p.risk_level}</Badge></td>
                  <td>
                    <Badge tone={ST[p.status] || "gray"}>{p.status}</Badge>
                    {p.overdue && <Badge tone="red">просрочен</Badge>}
                  </td>
                  <td className="muted">{p.due_at ? new Date(p.due_at).toLocaleString("ru-RU") : "—"}</td>
                  <td>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                      {p.status === "draft" && has("task.create") && p.risk_level !== "R1" && (
                        <button className="btn btn--sm" onClick={() => run(() => processApi.submitApproval(p.id), "На согласование")}>На согласование</button>
                      )}
                      {p.status === "pending_approval" && has("task.approve") && (
                        <button className="btn btn--sm" onClick={() => run(() => processApi.approve(p.id), "Согласовано")}>Согласовать</button>
                      )}
                      {(p.status === "draft" || p.status === "approved") && has("task.assign") && (
                        <>
                          <input className="input" placeholder="ID исполнителя" value={execId[p.id] || ""}
                                 onChange={(e) => setExecId({ ...execId, [p.id]: e.target.value })}
                                 style={{ width: 130 }} />
                          <button className="btn btn--sm" disabled={!execId[p.id]}
                                  onClick={() => run(() => processApi.assign(p.id, execId[p.id]!, p.due_at || undefined), "Назначено")}>Назначить</button>
                        </>
                      )}
                      {p.status === "assigned" && has("task.execute") && (
                        <button className="btn btn--sm" onClick={() => run(() => processApi.accept(p.id), "Принято в работу")}>Принять в работу</button>
                      )}
                      {(p.status === "accepted" || p.status === "revision_required") && has("task.execute") && (
                        <button className="btn btn--sm" onClick={() => run(() => processApi.start(p.id), "В работе")}>Начать</button>
                      )}
                      {p.status === "in_progress" && has("task.execute") && (
                        <button className="btn btn--sm" onClick={() => run(() => processApi.submitReview(p.id), "Отправлено на проверку")}>На проверку</button>
                      )}
                      {p.status === "submitted_for_review" && has("task.approve") && (
                        <>
                          <button className="btn btn--sm btn--primary" onClick={() => run(() => processApi.review(p.id, "completed"), "Закрыто проверяющим")}>Закрыть</button>
                          <button className="btn btn--sm" onClick={() => run(() => processApi.review(p.id, "revision_required", "на доработку"), "Возвращено")}>Вернуть</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={6} className="muted" style={{ padding: 18 }}>Процессов пока нет.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 14 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Разделение обязанностей: назначает постановщик, принимает исполнитель,
          <strong> закрывает только независимый проверяющий</strong>. Все переходы и
          согласования фиксируются в журнале аудита; проверки прав выполняются на сервере.
        </div>
      </div>
    </>
  );
}
