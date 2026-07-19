"use client";

/* «Контроль исполнения поручений» — рабочий контур (backend /task-control).
 * Доска контроля по статусам (просрочка, блокировки, ожидание, на проверке,
 * возвращены), препятствия/вопросы/эскалация/возврат, лента активности и
 * уведомления. Данные из backend, без mock; без backend — пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge, Risk } from "../../../../components/ui";
import { apiBaseConfigured } from "../../../../lib/authApi";
import {
  taskControlApi,
  type Board,
  type TaskCard,
  type Activity,
  type Notification,
} from "../../../../lib/taskControlApi";

const COLS: { key: keyof Board; label: string; tone: "red" | "amber" | "navy" | "emerald" }[] = [
  { key: "overdue", label: "Просрочены", tone: "red" },
  { key: "blocked", label: "Заблокированы", tone: "red" },
  { key: "waiting_for_information", label: "Ждут информации", tone: "amber" },
  { key: "in_progress", label: "В работе", tone: "navy" },
  { key: "pending_review", label: "На проверке", tone: "amber" },
  { key: "returned_for_revision", label: "На доработке", tone: "amber" },
];

export default function TaskControlPage() {
  const live = apiBaseConfigured();
  const [board, setBoard] = useState<Board | null>(null);
  const [notes, setNotes] = useState<Notification[]>([]);
  const [sel, setSel] = useState<TaskCard | null>(null);
  const [feed, setFeed] = useState<Activity[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    taskControlApi.board().then(setBoard).catch(() => undefined);
    taskControlApi.notifications().then(setNotes).catch(() => undefined);
  };
  useEffect(() => { if (live) reload(); }, [live]);
  useEffect(() => { if (live && sel) taskControlApi.activity(sel.id).then(setFeed).catch(() => undefined); else setFeed([]); }, [live, sel]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); if (sel) { taskControlApi.activity(sel.id).then(setFeed); } }
    catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Контроль исполнения поручений" desc="Просрочка, препятствия, эскалация, доработка" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  const total = board ? COLS.reduce((s, c) => s + board[c.key].length, 0) : 0;
  const unread = notes.filter((n) => !n.read_at).length;

  return (
    <>
      <PageHead title="Контроль исполнения поручений" desc="Доска контроля, препятствия, эскалация, доработка · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="На контроле" value={String(total)} icon="tasks" tone="navy" foot="активные поручения" />
        <Kpi label="Просрочено" value={String(board?.overdue.length ?? 0)} icon="approvals" tone={board && board.overdue.length ? "amber" : "emerald"} foot="нарушен срок" />
        <Kpi label="Заблокировано" value={String(board?.blocked.length ?? 0)} icon="reports" tone={board && board.blocked.length ? "amber" : "emerald"} foot="есть препятствия" />
        <Kpi label="Уведомления" value={String(unread)} icon="documents" tone={unread ? "amber" : "emerald"} foot="непрочитанные" />
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14, marginBottom: 18 }}>
        {board && COLS.map((c) => (
          <Card key={c.key} title={`${c.label} · ${board[c.key].length}`} flush>
            <div style={{ display: "grid", gap: 8, padding: 12 }}>
              {board[c.key].length === 0 && <span className="muted" style={{ fontSize: 12 }}>Нет поручений.</span>}
              {board[c.key].map((t) => (
                <button key={t.id} onClick={() => setSel(t)} style={{ textAlign: "left", border: "1px solid var(--line,#e2e8f0)", borderRadius: 8, padding: "8px 10px", background: sel?.id === t.id ? "var(--emerald-50)" : "#fff", cursor: "pointer" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{t.title}</span>
                    <Risk level={t.risk_level as "R0" | "R1" | "R2" | "R3" | "R4"} />
                  </div>
                  <div style={{ display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                    <Badge tone={c.tone}>{t.status}</Badge>
                    {t.escalation_level > 0 && <Badge tone="red">эск. {t.escalation_level}</Badge>}
                    {t.blocked_reason && <span className="muted" style={{ fontSize: 11 }}>⛔ {t.blocked_reason}</span>}
                  </div>
                </button>
              ))}
            </div>
          </Card>
        ))}
      </div>

      {sel && (
        <Card title={`Поручение: ${sel.title} · ${sel.status}`} flush className="span-2">
          <div style={{ display: "flex", gap: 8, padding: "12px 16px", flexWrap: "wrap" }}>
            {sel.status === "blocked" && <button className="btn btn--emerald btn--sm" onClick={() => run(() => taskControlApi.resolveBlocker(sel.id), "Препятствие снято")}>Снять препятствие</button>}
            {sel.status === "waiting_for_information" && <button className="btn btn--emerald btn--sm" onClick={() => { const m = prompt("Ответ:"); if (m) run(() => taskControlApi.answer(sel.id, m), "Ответ отправлен"); }}>Ответить</button>}
            {["pending_review"].includes(sel.status) && <button className="btn btn--ghost btn--sm" onClick={() => { const m = prompt("Причина возврата:"); if (m) run(() => taskControlApi.returnForRevision(sel.id, m), "Возвращено на доработку"); }}>Вернуть на доработку</button>}
            <button className="btn btn--ghost btn--sm" onClick={() => run(() => taskControlApi.escalate(sel.id), "Эскалировано")}>Эскалировать</button>
            <button className="btn btn--ghost btn--sm" onClick={() => { const m = prompt("Комментарий:"); if (m) run(() => taskControlApi.comment(sel.id, m), "Комментарий добавлен"); }}>Комментарий</button>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Время</th><th>Событие</th><th>Сообщение</th></tr></thead>
              <tbody>
                {feed.length === 0 && <tr><td colSpan={3} className="muted" style={{ padding: 16 }}>Активности нет.</td></tr>}
                {feed.map((u) => (
                  <tr key={u.id}>
                    <td className="table__muted">{new Date(u.created_at).toLocaleString("ru-RU")}</td>
                    <td><Badge tone={u.update_type === "blocker" || u.update_type === "escalation" ? "red" : u.update_type === "answer" ? "emerald" : "gray"}>{u.update_type}</Badge></td>
                    <td>{u.message || "—"}{u.blocker_category ? ` (${u.blocker_category})` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div style={{ height: 18 }} />
      <Card title="Мои уведомления" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Приоритет</th><th>Заголовок</th><th>Сообщение</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {notes.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Уведомлений нет.</td></tr>}
              {notes.map((n) => (
                <tr key={n.id} style={n.read_at ? { opacity: 0.6 } : undefined}>
                  <td><Badge tone={n.priority === "high" ? "red" : "gray"}>{n.priority}</Badge></td>
                  <td className="table__strong">{n.title}</td>
                  <td className="table__muted">{n.message}</td>
                  <td>{n.read_at ? <Badge tone="emerald">прочитано</Badge> : <Badge tone="amber">новое</Badge>}</td>
                  <td>{!n.read_at && <button className="btn btn--ghost btn--sm" onClick={() => run(() => taskControlApi.readNotification(n.id), "Отмечено прочитанным")}>Прочитано</button>}</td>
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
          Исполнитель фиксирует препятствия и вопросы (право <strong>task.execute</strong>); контролёр
          отвечает, снимает препятствия и эскалирует (<strong>task.assign</strong>); руководитель
          возвращает на доработку (<strong>task.approve</strong>). Просрочка определяется по сроку;
          доступ ограничен доступными проектами. Ответственные получают уведомления. Все действия —
          в журнале аудита.
        </div>
      </div>
    </>
  );
}
