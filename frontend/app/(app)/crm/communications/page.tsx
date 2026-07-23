"use client";

/* Центр коммуникаций (backend /communications). Вкладки: Входящие, Исходящие,
 * Черновики, Рассылки, Шаблоны, Контакты, Каналы, Журнал доставки. Реальные данные
 * из backend; реальная отправка на сервере выключена (sandbox). Права проверяются
 * на сервере (communication.view/manage/approve/send). */
import { useCallback, useEffect, useState } from "react";
import { PageHead, Card, Badge } from "../../../../components/ui";
import { apiBaseConfigured, me } from "../../../../lib/authApi";
import {
  commApi,
  type CommMessage,
  type CommContact,
  type CommTemplate,
  type CommChannel,
  type DeliveryEvent,
} from "../../../../lib/commApi";

type Tab = "inbox" | "outbox" | "drafts" | "broadcasts" | "templates" | "contacts" | "channels";
const TABS: { id: Tab; label: string }[] = [
  { id: "inbox", label: "Входящие" },
  { id: "outbox", label: "Исходящие" },
  { id: "drafts", label: "Черновики" },
  { id: "broadcasts", label: "Рассылки" },
  { id: "templates", label: "Шаблоны" },
  { id: "contacts", label: "Контакты" },
  { id: "channels", label: "Каналы" },
];
const CHANNELS = ["email", "whatsapp", "instagram", "telegram", "internal"];
const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  draft: "gray", pending_approval: "amber", approved: "navy", scheduled: "navy",
  sending: "amber", sent: "emerald", delivered: "emerald", read: "emerald",
  failed: "red", cancelled: "gray",
};

export default function CommunicationsPage() {
  const live = apiBaseConfigured();
  const [tab, setTab] = useState<Tab>("outbox");
  const [perms, setPerms] = useState<string[]>([]);
  const [msgs, setMsgs] = useState<CommMessage[]>([]);
  const [contacts, setContacts] = useState<CommContact[]>([]);
  const [templates, setTemplates] = useState<CommTemplate[]>([]);
  const [channels, setChannels] = useState<CommChannel[]>([]);
  const [log, setLog] = useState<{ id: string; events: DeliveryEvent[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ch, setCh] = useState("email");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [addr, setAddr] = useState("");

  const has = (p: string) => perms.includes("system_owner") || perms.includes(p);

  const reload = useCallback(() => {
    if (!live) return;
    if (tab === "inbox") commApi.inbox().then(setMsgs).catch(() => undefined);
    else if (tab === "outbox") commApi.outbox().then(setMsgs).catch(() => undefined);
    else if (tab === "drafts") commApi.drafts().then(setMsgs).catch(() => undefined);
    else if (tab === "contacts") commApi.contacts().then(setContacts).catch(() => undefined);
    else if (tab === "templates") commApi.templates().then(setTemplates).catch(() => undefined);
    else if (tab === "channels") commApi.channels().then(setChannels).catch(() => undefined);
  }, [live, tab]);

  useEffect(() => {
    if (!live) return;
    me().then((u) => setPerms(u.permissions)).catch(() => undefined);
  }, [live]);
  useEffect(() => { reload(); }, [reload]);

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try { await fn(); reload(); } catch (e) { setErr((e as Error).message); }
  }

  async function createDraft() {
    if (!addr.trim()) { setErr("Укажите адрес получателя"); return; }
    await run(async () => {
      await commApi.createMessage({
        channel: ch, subject: subject || undefined, body_text: body || undefined,
        recipients: [{ address: addr }],
      });
      setSubject(""); setBody(""); setAddr("");
      setTab("drafts");
    });
  }

  async function showLog(id: string) {
    try { setLog({ id, events: await commApi.deliveryLog(id) }); }
    catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Центр коммуникаций" desc="Единый контур сообщений и рассылок" />
        <Card title="Backend не настроен">
          <p className="muted">Экран работает при подключённом backend.</p>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Центр коммуникаций"
        desc="Единый контур сообщений по каналам (email, WhatsApp, Instagram, Telegram, внутренние). Реальная отправка выключена — безопасный sandbox до подключения ключей."
      />

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {TABS.map((t) => (
          <button key={t.id}
                  className={`btn btn--sm ${tab === t.id ? "btn--primary" : ""}`}
                  onClick={() => { setTab(t.id); setLog(null); }}>
            {t.label}
          </button>
        ))}
      </div>

      {err && (
        <div className="alert" style={{ marginBottom: 12 }}>
          <div className="alert__icon">⚠</div>
          <div className="muted" style={{ fontSize: 13 }}>{err}</div>
        </div>
      )}

      {tab === "drafts" && has("communication.manage") && (
        <Card title="Новое сообщение" flush>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: 14, alignItems: "center" }}>
            <select className="input" value={ch} onChange={(e) => setCh(e.target.value)}>
              {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input className="input" placeholder="Адрес получателя" value={addr}
                   onChange={(e) => setAddr(e.target.value)} style={{ minWidth: 200 }} />
            <input className="input" placeholder="Тема" value={subject}
                   onChange={(e) => setSubject(e.target.value)} style={{ minWidth: 180 }} />
            <input className="input" placeholder="Текст" value={body}
                   onChange={(e) => setBody(e.target.value)} style={{ minWidth: 220 }} />
            <button className="btn btn--primary btn--sm" onClick={createDraft}>Создать черновик</button>
          </div>
        </Card>
      )}

      {tab === "broadcasts" && (
        <div className="alert">
          <div className="alert__icon">ℹ</div>
          <div className="muted" style={{ fontSize: 13 }}>
            Рассылки (выбор канала, групп контактов, шаблона, вложений, планирование,
            согласование и отчёт о доставке) готовятся отдельным этапом. Модель сообщений
            и журнал доставки уже работают.
          </div>
        </div>
      )}

      {(tab === "inbox" || tab === "outbox" || tab === "drafts") && (
        <Card title={`Сообщения — ${msgs.length}`} flush className="span-2" style={{ marginTop: 12 }}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Канал</th><th>Тема</th><th>Статус</th><th>Внешний ID</th><th>Действия</th></tr></thead>
              <tbody>
                {msgs.map((m) => (
                  <tr key={m.id}>
                    <td className="muted">{m.channel}</td>
                    <td className="table__strong">{m.subject || "(без темы)"}</td>
                    <td><Badge tone={ST[m.status] || "gray"}>{m.status}</Badge></td>
                    <td className="muted" style={{ fontSize: 11 }}>{m.external_id || "—"}</td>
                    <td>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {m.status === "draft" && has("communication.manage") && (
                          <button className="btn btn--sm" onClick={() => run(() => commApi.submitApproval(m.id))}>На согласование</button>
                        )}
                        {m.status === "pending_approval" && has("communication.approve") && (
                          <button className="btn btn--sm" onClick={() => run(() => commApi.approve(m.id))}>Согласовать</button>
                        )}
                        {(m.status === "approved" || m.status === "scheduled") && has("communication.send") && (
                          <button className="btn btn--sm btn--primary" onClick={() => run(() => commApi.send(m.id))}>Отправить</button>
                        )}
                        {m.status === "failed" && has("communication.send") && (
                          <button className="btn btn--sm" onClick={() => run(() => commApi.retry(m.id))}>Повтор</button>
                        )}
                        <button className="btn btn--sm" onClick={() => showLog(m.id)}>Журнал</button>
                      </div>
                    </td>
                  </tr>
                ))}
                {msgs.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Сообщений нет.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === "contacts" && (
        <Card title={`Контакты — ${contacts.length}`} flush className="span-2" style={{ marginTop: 12 }}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Имя</th><th>Email</th><th>Телефон</th><th>Согласие</th><th>Стоп-лист</th></tr></thead>
              <tbody>
                {contacts.map((c) => (
                  <tr key={c.id}>
                    <td className="table__strong">{c.display_name}</td>
                    <td className="muted">{c.email || "—"}</td>
                    <td className="muted">{c.phone || "—"}</td>
                    <td>{c.consent ? <Badge tone="emerald">да</Badge> : <Badge tone="gray">нет</Badge>}</td>
                    <td>{c.stop_listed ? <Badge tone="red">да</Badge> : <Badge tone="gray">нет</Badge>}</td>
                  </tr>
                ))}
                {contacts.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Контактов нет.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === "templates" && (
        <Card title={`Шаблоны — ${templates.length}`} flush className="span-2" style={{ marginTop: 12 }}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Код</th><th>Название</th><th>Канал</th><th>Утверждён</th></tr></thead>
              <tbody>
                {templates.map((t) => (
                  <tr key={t.id}>
                    <td className="muted">{t.code}</td>
                    <td className="table__strong">{t.name}</td>
                    <td className="muted">{t.channel}</td>
                    <td>{t.is_approved ? <Badge tone="emerald">да</Badge> : <Badge tone="amber">нет</Badge>}</td>
                  </tr>
                ))}
                {templates.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Шаблонов нет.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === "channels" && (
        <Card title={`Каналы — ${channels.length}`} flush className="span-2" style={{ marginTop: 12 }}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Код</th><th>Канал</th><th>Провайдер</th><th>Статус</th><th>Ключи</th></tr></thead>
              <tbody>
                {channels.map((c) => (
                  <tr key={c.id}>
                    <td className="muted">{c.code}</td>
                    <td className="table__strong">{c.channel}</td>
                    <td className="muted">{c.provider || "—"}</td>
                    <td><Badge tone={c.status === "active" ? "emerald" : "gray"}>{c.status}</Badge></td>
                    <td>{c.credentials_configured_externally ? <Badge tone="emerald">подключены</Badge> : <Badge tone="amber">нет (sandbox)</Badge>}</td>
                  </tr>
                ))}
                {channels.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Каналы не настроены. До подключения ключей отправка идёт в sandbox.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {log && (
        <Card title="Журнал доставки" flush className="span-2" style={{ marginTop: 12 }}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Событие</th><th>Детали</th><th>Внешний ID</th><th>Время</th></tr></thead>
              <tbody>
                {log.events.map((e) => (
                  <tr key={e.id}>
                    <td><Badge tone={e.event === "failed" ? "red" : e.event === "skipped" ? "amber" : "navy"}>{e.event}</Badge></td>
                    <td className="muted">{e.detail || "—"}</td>
                    <td className="muted" style={{ fontSize: 11 }}>{e.external_id || "—"}</td>
                    <td className="muted">{new Date(e.occurred_at).toLocaleString("ru-RU")}</td>
                  </tr>
                ))}
                {log.events.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Событий нет.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
