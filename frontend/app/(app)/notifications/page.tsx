"use client";

/* «Уведомления» (backend /notifications). Персональный центр in-app уведомлений:
 * список, счётчик непрочитанных, отметка прочитанным. Данные из backend, без mock;
 * без backend — честное пустое состояние. Внешняя рассылка здесь не выполняется. */
import { useEffect, useState } from "react";
import { PageHead, Card, Badge } from "../../../components/ui";
import { apiBaseConfigured } from "../../../lib/authApi";
import { notificationsApi, type Notification } from "../../../lib/notificationsApi";

const PRI: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  low: "gray", normal: "navy", high: "amber", critical: "red",
};

export default function NotificationsPage() {
  const live = apiBaseConfigured();
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    notificationsApi.list(onlyUnread).then(setItems).catch(() => undefined);
    notificationsApi.unreadCount().then((r) => setUnread(r.unread)).catch(() => undefined);
  };
  useEffect(() => {
    if (!live) return;
    notificationsApi.list(onlyUnread).then(setItems).catch(() => undefined);
    notificationsApi.unreadCount().then((r) => setUnread(r.unread)).catch(() => undefined);
  }, [live, onlyUnread]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Уведомления" desc="Персональные уведомления системы" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает уведомления из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="Уведомления" desc={`Персональные уведомления · непрочитанных: ${unread}`} />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        <button className={`btn btn--sm ${onlyUnread ? "btn--ghost" : "btn--primary"}`} onClick={() => setOnlyUnread(false)}>Все</button>
        <button className={`btn btn--sm ${onlyUnread ? "btn--primary" : "btn--ghost"}`} onClick={() => setOnlyUnread(true)}>Непрочитанные</button>
        <div style={{ flex: 1 }} />
        {unread > 0 && <button className="btn btn--emerald btn--sm" onClick={() => run(() => notificationsApi.markAllRead(), "Все отмечены прочитанными")}>Отметить все прочитанными</button>}
      </div>

      <Card title="Лента уведомлений" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Приоритет</th><th>Заголовок</th><th>Сообщение</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Уведомлений нет.</td></tr>}
              {items.map((n) => (
                <tr key={n.id} style={{ opacity: n.read_at ? 0.6 : 1 }}>
                  <td><Badge tone={PRI[n.priority] || "gray"}>{n.priority}</Badge></td>
                  <td className="table__strong">{n.title || "—"}</td>
                  <td className="table__muted">{n.message || "—"}</td>
                  <td>{n.read_at ? <Badge tone="gray">прочитано</Badge> : <Badge tone="amber">новое</Badge>}</td>
                  <td>{!n.read_at && <button className="btn btn--ghost btn--sm" onClick={() => run(() => notificationsApi.markRead(n.id), "Отмечено прочитанным")}>Прочитано</button>}</td>
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
          Это внутренний центр уведомлений (канал <strong>in-app</strong>): система
          показывает уведомления внутри интерфейса и <strong>не отправляет</strong>
          внешних писем и сообщений (§14). Пользователь видит только свои уведомления.
          Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}
