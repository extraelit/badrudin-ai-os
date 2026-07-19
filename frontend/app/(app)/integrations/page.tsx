"use client";

/* «Масштабирование интеграций» — внутренний контур (backend /integrations).
 * Реестр коннекторов и очередь исходящих сообщений как черновиков на утверждение.
 * Отправка не производится, секреты не хранятся. Данные из backend, без mock;
 * без backend — честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured } from "../../../lib/authApi";
import {
  integrationApi,
  type Connector,
  type Outbound,
  type IntegrationSummary,
} from "../../../lib/integrationApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  draft: "gray", configured: "emerald", disabled: "red",
  pending_approval: "amber", approved: "emerald", cancelled: "gray",
};
const CH = ["email", "telegram", "whatsapp_business", "instagram", "webhook", "internal"];

export default function IntegrationsPage() {
  const live = apiBaseConfigured();
  const [sum, setSum] = useState<IntegrationSummary | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [outbound, setOutbound] = useState<Outbound[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("email");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    integrationApi.summary().then(setSum).catch(() => undefined);
    integrationApi.listConnectors().then(setConnectors).catch(() => undefined);
    integrationApi.listOutbound().then(setOutbound).catch(() => undefined);
  };
  useEffect(() => { if (live) reload(); }, [live]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Масштабирование интеграций" desc="Реестр коннекторов и исходящие сообщения — черновики на утверждение" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="Масштабирование интеграций" desc="Коннекторы и исходящие сообщения — черновики на утверждение, без отправки · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Коннекторы" value={String(sum?.connectors_total ?? "—")} icon="agents" tone="navy" foot={`настроено: ${sum?.connectors_configured ?? 0}`} />
        <Kpi label="Черновики" value={String(sum?.outbound_draft ?? "—")} icon="documents" tone="gray" foot="исходящие" />
        <Kpi label="На утверждении" value={String(sum?.outbound_pending ?? "—")} icon="approvals" tone={sum && sum.outbound_pending ? "amber" : "emerald"} foot="ждут решения" />
        <Kpi label="Утверждено" value={String(sum?.outbound_approved ?? "—")} icon="reports" tone="emerald" foot="готово к отправке вне системы" />
      </div>

      <Card title="Реестр коннекторов (без секретов)" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Код" value={code} onChange={(e) => setCode(e.target.value)} style={{ ...inp, maxWidth: 160 }} />
          <input placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} style={inp} />
          <select value={channel} onChange={(e) => setChannel(e.target.value)} style={sel}>{CH.map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <button className="btn btn--primary btn--sm" onClick={() => { if (code && name) { run(() => integrationApi.registerConnector({ code, name, channel }), "Коннектор добавлен"); setCode(""); setName(""); } }}><Icons.plus width={16} height={16} /> Добавить</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Код</th><th>Название</th><th>Канал</th><th>Статус</th><th>Доступы</th><th>Действие</th></tr></thead>
            <tbody>
              {connectors.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Коннекторов нет.</td></tr>}
              {connectors.map((c) => (
                <tr key={c.id}>
                  <td className="table__muted">{c.code}</td>
                  <td className="table__strong">{c.name}</td>
                  <td>{c.channel}</td>
                  <td><Badge tone={ST[c.status] || "gray"}>{c.status}</Badge></td>
                  <td>{c.credentials_configured_externally ? <Badge tone="emerald">настроены вне системы</Badge> : <Badge tone="gray">нет</Badge>}</td>
                  <td>
                    {c.status !== "configured"
                      ? <button className="btn btn--emerald btn--sm" onClick={() => run(() => integrationApi.setConnectorStatus(c.id, "configured", true), "Коннектор помечен настроенным")}>Отметить настроенным</button>
                      : <button className="btn btn--ghost btn--sm" onClick={() => run(() => integrationApi.setConnectorStatus(c.id, "disabled"), "Коннектор отключён")}>Отключить</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Исходящие сообщения (черновики на утверждение)" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Тема" value={subject} onChange={(e) => setSubject(e.target.value)} style={{ ...inp, maxWidth: 220 }} />
          <input placeholder="Текст сообщения" value={body} onChange={(e) => setBody(e.target.value)} style={inp} />
          <button className="btn btn--primary btn--sm" onClick={() => { if (subject || body) { run(() => integrationApi.createDraft({ channel: "email", subject, body_text: body }), "Черновик создан"); setSubject(""); setBody(""); } }}>Создать черновик</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Канал</th><th>Тема</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {outbound.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Исходящих нет.</td></tr>}
              {outbound.map((m) => (
                <tr key={m.id}>
                  <td className="table__muted">{m.channel}</td>
                  <td className="table__strong">{m.subject || "—"}</td>
                  <td><Badge tone={ST[m.status] || "gray"}>{m.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {m.status === "draft" && <button className="btn btn--ghost btn--sm" onClick={() => run(() => integrationApi.submit(m.id), "Отправлено на утверждение")}>На утверждение</button>}
                    {m.status === "pending_approval" && (
                      <>
                        <button className="btn btn--emerald btn--sm" onClick={() => run(() => integrationApi.decide(m.id, "approved"), "Утверждено (готово к отправке вне системы)")}>Утвердить</button>
                        <button className="btn btn--ghost btn--sm" onClick={() => { const c = prompt("Причина отклонения:") || undefined; run(() => integrationApi.decide(m.id, "rejected", c), "Отклонено"); }}>Отклонить</button>
                      </>
                    )}
                    {m.status === "approved" && <span className="muted" style={{ fontSize: 12 }}>✓ готово к отправке вне системы</span>}
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
          Внутренний контур: система <strong>не отправляет</strong> письма и сообщения и
          <strong> не хранит секретов</strong>. Реальные доступы настраиваются вне системы и
          отмечаются признаком. Важная внешняя коммуникация сначала формируется как черновик и
          отправляется только после утверждения человеком (§14); статус «утверждено» означает
          готовность к отправке уполномоченным человеком/коннектором вне модуля. Доступ:
          <strong> integration.view</strong> / <strong>integration.manage</strong> /
          <strong> integration.approve</strong>. Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 170, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
const sel: React.CSSProperties = { padding: "8px 10px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
