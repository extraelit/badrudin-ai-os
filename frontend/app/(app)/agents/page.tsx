"use client";

/* «Оркестратор ИИ-агентов» — рабочий контур (backend /agents). Реестр агентов,
 * запуски и предложения агентов с обязательным человеческим утверждением и
 * применением через общий сервис. Данные из backend, без mock; без backend —
 * честное пустое состояние. Фактический вызов модели — отдельный коннектор. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge, Risk } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured } from "../../../lib/authApi";
import { agentsApi, type Agent, type Proposal, type AgentSummary } from "../../../lib/agentsApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  active: "emerald", inactive: "gray", suspended: "red",
  pending: "amber", approved: "navy", rejected: "red", applied: "emerald",
};

export default function AgentsPage() {
  const live = apiBaseConfigured();
  const [sum, setSum] = useState<AgentSummary | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    agentsApi.summary().then(setSum).catch(() => undefined);
    agentsApi.list().then(setAgents).catch(() => undefined);
    agentsApi.proposals().then(setProposals).catch(() => undefined);
  };
  useEffect(() => { if (live) reload(); }, [live]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Оркестратор ИИ-агентов" desc="Реестр агентов, запуски и предложения под контролем человека" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="Оркестратор ИИ-агентов" desc="Агенты предлагают — человек утверждает · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Агенты" value={String(sum?.agents_total ?? "—")} icon="agents" tone="navy" foot={`активны: ${sum?.agents_active ?? 0}`} />
        <Kpi label="Предложений на решении" value={String(sum?.proposals_pending ?? "—")} icon="approvals" tone={sum && sum.proposals_pending ? "amber" : "emerald"} foot="ждут человека" />
        <Kpi label="Утверждено" value={String(sum?.proposals_approved ?? "—")} icon="reports" tone="emerald" foot="принято/применено" />
        <Kpi label="Отклонено" value={String(sum?.proposals_rejected ?? "—")} icon="documents" tone="gray" foot="не приняты" />
      </div>

      <Card title="Реестр агентов" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Код агента" value={code} onChange={(e) => setCode(e.target.value)} style={{ ...inp, maxWidth: 200 }} />
          <input placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} style={inp} />
          <button className="btn btn--primary btn--sm" onClick={() => { if (code && name) { run(() => agentsApi.register({ code, name }), "Агент зарегистрирован"); setCode(""); setName(""); } }}><Icons.plus width={16} height={16} /> Добавить</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Код</th><th>Название</th><th>Статус</th><th>Риск</th><th>Контроль</th><th>Действие</th></tr></thead>
            <tbody>
              {agents.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Агентов нет.</td></tr>}
              {agents.map((a) => (
                <tr key={a.id}>
                  <td className="table__muted">{a.code}</td>
                  <td className="table__strong">{a.name}</td>
                  <td><Badge tone={ST[a.status] || "gray"}>{a.status}</Badge></td>
                  <td><Risk level={a.default_risk_level as "R0" | "R1" | "R2" | "R3" | "R4"} /></td>
                  <td>{a.requires_human_approval ? <Badge tone="navy">человек</Badge> : <Badge tone="amber">авто</Badge>}</td>
                  <td>
                    {a.status !== "active"
                      ? <button className="btn btn--emerald btn--sm" onClick={() => run(() => agentsApi.setStatus(a.id, "active"), "Агент активирован")}>Активировать</button>
                      : <button className="btn btn--ghost btn--sm" onClick={() => run(() => agentsApi.setStatus(a.id, "inactive"), "Агент остановлен")}>Остановить</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Предложения агентов (решение человека)" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Тип</th><th>Заголовок</th><th>Риск</th><th>Статус</th><th>Решение человека</th></tr></thead>
            <tbody>
              {proposals.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Предложений нет.</td></tr>}
              {proposals.map((p) => (
                <tr key={p.id}>
                  <td><Badge tone="navy">{p.proposal_type}</Badge></td>
                  <td className="table__strong">{p.title}</td>
                  <td><Risk level={p.risk_level as "R0" | "R1" | "R2" | "R3" | "R4"} /></td>
                  <td><Badge tone={ST[p.status] || "gray"}>{p.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {p.status === "pending" && (
                      <>
                        <button className="btn btn--emerald btn--sm" onClick={() => run(() => agentsApi.review(p.id, "approved"), "Утверждено человеком")}>Утвердить</button>
                        <button className="btn btn--ghost btn--sm" onClick={() => { const c = prompt("Причина отклонения:") || undefined; run(() => agentsApi.review(p.id, "rejected", c), "Отклонено"); }}>Отклонить</button>
                      </>
                    )}
                    {p.status === "approved" && <button className="btn btn--emerald btn--sm" onClick={() => run(() => agentsApi.apply(p.id), "Предложение применено")}>Применить</button>}
                    {p.status === "applied" && <span className="muted" style={{ fontSize: 12 }}>→ {p.applied_entity_type}</span>}
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
          Агент действует только в пределах своей роли и не имеет права окончательного решения:
          каждое предложение проходит утверждение человеком, применение переиспользует общие сервисы
          (например, создание поручения), не дублируя сущности. Запуски и решения фиксируются в
          журнале аудита. Фактический вызов языковой модели выполняется отдельным утверждённым
          коннектором (провайдер настраивается после юридической проверки). Доступ:
          <strong> agent.view</strong> / <strong>agent.manage</strong> (реестр, запуск, предложения) /
          <strong> agent.approve</strong> (утверждение).
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 160, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
