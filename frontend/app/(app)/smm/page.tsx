"use client";

/* «SMM и внешние публикации» — внутренний контур (backend /smm).
 * Контент-план и публикации как черновики на утверждение. Публикация не
 * производится, секреты не хранятся. Данные из backend, без mock; без backend —
 * честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured } from "../../../lib/authApi";
import {
  smmApi,
  type PlanItem,
  type Publication,
  type SmmSummary,
} from "../../../lib/smmApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  idea: "gray", planned: "navy", in_progress: "amber", done: "emerald", cancelled: "gray",
  draft: "gray", fact_check: "navy", pending_approval: "amber",
  approved: "emerald", scheduled: "emerald",
};
const CH = ["instagram", "telegram", "whatsapp_business", "email", "webhook", "internal"];

export default function SmmPage() {
  const live = apiBaseConfigured();
  const [sum, setSum] = useState<SmmSummary | null>(null);
  const [plan, setPlan] = useState<PlanItem[]>([]);
  const [pubs, setPubs] = useState<Publication[]>([]);
  const [ptitle, setPtitle] = useState("");
  const [pchannel, setPchannel] = useState("instagram");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    smmApi.summary().then(setSum).catch(() => undefined);
    smmApi.listPlan().then(setPlan).catch(() => undefined);
    smmApi.listPublications().then(setPubs).catch(() => undefined);
  };
  useEffect(() => { if (live) reload(); }, [live]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  const checksReady = (p: Publication) => p.rights_confirmed && p.pii_checked && p.legal_checked;

  if (!live) {
    return (
      <>
        <PageHead title="SMM и внешние публикации" desc="Контент-план и публикации — черновики на утверждение, без публикации" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="SMM и внешние публикации" desc="Контент-план и публикации — черновики на утверждение, без публикации · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Контент-план" value={String(sum?.plan_total ?? "—")} icon="documents" tone="navy" foot={`в работе: ${sum?.plan_active ?? 0}`} />
        <Kpi label="Черновики" value={String(sum?.publications_draft ?? "—")} icon="documents" tone="gray" foot="публикации" />
        <Kpi label="На утверждении" value={String(sum?.publications_pending ?? "—")} icon="approvals" tone={sum && sum.publications_pending ? "amber" : "emerald"} foot="ждут решения" />
        <Kpi label="Утверждено" value={String(sum?.publications_approved ?? "—")} icon="reports" tone="emerald" foot="готово к публикации вне системы" />
      </div>

      <Card title="Контент-план (идеи публикаций)" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Идея / тема" value={ptitle} onChange={(e) => setPtitle(e.target.value)} style={inp} />
          <select value={pchannel} onChange={(e) => setPchannel(e.target.value)} style={sel}>{CH.map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <button className="btn btn--primary btn--sm" onClick={() => { if (ptitle) { run(() => smmApi.createPlan({ title: ptitle, channel: pchannel }), "Идея добавлена в план"); setPtitle(""); } }}><Icons.plus width={16} height={16} /> Добавить</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Идея</th><th>Канал</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {plan.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Плана нет.</td></tr>}
              {plan.map((i) => (
                <tr key={i.id}>
                  <td className="table__strong">{i.title}</td>
                  <td>{i.channel}</td>
                  <td><Badge tone={ST[i.status] || "gray"}>{i.status}</Badge></td>
                  <td>
                    {i.status === "idea" && <button className="btn btn--ghost btn--sm" onClick={() => run(() => smmApi.setPlanStatus(i.id, "planned"), "Запланировано")}>Запланировать</button>}
                    {i.status === "planned" && <button className="btn btn--ghost btn--sm" onClick={() => run(() => smmApi.setPlanStatus(i.id, "in_progress"), "В работе")}>В работу</button>}
                    {i.status === "in_progress" && <button className="btn btn--emerald btn--sm" onClick={() => run(() => smmApi.setPlanStatus(i.id, "done"), "Готово")}>Готово</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Публикации (черновики на утверждение)" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Заголовок" value={title} onChange={(e) => setTitle(e.target.value)} style={{ ...inp, maxWidth: 220 }} />
          <input placeholder="Текст публикации" value={body} onChange={(e) => setBody(e.target.value)} style={inp} />
          <button className="btn btn--primary btn--sm" onClick={() => { if (title || body) { run(() => smmApi.createPublication({ channel: pchannel, title, body_text: body }), "Черновик создан"); setTitle(""); setBody(""); } }}>Создать черновик</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Заголовок</th><th>Канал</th><th>Проверки</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {pubs.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Публикаций нет.</td></tr>}
              {pubs.map((p) => (
                <tr key={p.id}>
                  <td className="table__strong">{p.title || "—"}</td>
                  <td className="table__muted">{p.channel}</td>
                  <td style={{ fontSize: 12 }}>
                    <Badge tone={p.rights_confirmed ? "emerald" : "gray"}>права</Badge>{" "}
                    <Badge tone={p.pii_checked ? "emerald" : "gray"}>ПДн</Badge>{" "}
                    <Badge tone={p.legal_checked ? "emerald" : "gray"}>юр.</Badge>
                  </td>
                  <td><Badge tone={ST[p.status] || "gray"}>{p.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {(p.status === "draft" || p.status === "fact_check") && !checksReady(p) &&
                      <button className="btn btn--ghost btn--sm" onClick={() => run(() => smmApi.setChecks(p.id, { rights_confirmed: true, pii_checked: true, legal_checked: true }), "Проверки отмечены")}>Отметить проверки</button>}
                    {(p.status === "draft" || p.status === "fact_check") && checksReady(p) &&
                      <button className="btn btn--ghost btn--sm" onClick={() => run(() => smmApi.submit(p.id), "Отправлено на утверждение")}>На утверждение</button>}
                    {p.status === "pending_approval" && (
                      <>
                        <button className="btn btn--emerald btn--sm" onClick={() => run(() => smmApi.decide(p.id, "approved"), "Утверждено (готово к публикации вне системы)")}>Утвердить</button>
                        <button className="btn btn--ghost btn--sm" onClick={() => { const c = prompt("Причина отклонения:") || undefined; run(() => smmApi.decide(p.id, "rejected", c), "Отклонено"); }}>Отклонить</button>
                      </>
                    )}
                    {(p.status === "approved" || p.status === "scheduled") && <span className="muted" style={{ fontSize: 12 }}>✓ готово к публикации вне системы</span>}
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
          Внутренний контур: система <strong>не публикует</strong> материалы в социальных
          сетях и <strong>не хранит секретов</strong>. Публикация возможна только после
          проверки прав на материалы, персональных данных и юридической/репутационной
          проверки, а также утверждения человеком (§14). Статус «утверждено»/«запланировано»
          означает готовность к публикации официальным утверждённым инструментом вне модуля.
          Доступ: <strong>smm.view</strong> / <strong>smm.manage</strong> /
          <strong> smm.approve</strong>. Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 170, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
const sel: React.CSSProperties = { padding: "8px 10px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
