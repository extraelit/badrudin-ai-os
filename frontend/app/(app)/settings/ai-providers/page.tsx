"use client";

/* Настройки → ИИ-провайдеры (backend /ai-providers). Включение/отключение
 * провайдера, модель по умолчанию, проверка подключения, назначение модели
 * агентам, стоимость и расход. Ключи маскируются (не передаются в интерфейс).
 * Реальные вызовы ИИ по умолчанию выключены (эхо-режим). Права — на сервере. */
import { useEffect, useState } from "react";
import { PageHead, Card, Badge } from "../../../../components/ui";
import { apiBaseConfigured, me } from "../../../../lib/authApi";
import {
  aiProviderApi,
  agentsList,
  type AIProvider,
  type AIUsage,
  type AgentRef,
} from "../../../../lib/aiProviderApi";

const CODES = ["openai", "anthropic", "gemini", "local"];
const HEALTH: Record<string, "gray" | "emerald" | "red"> = {
  unknown: "gray", ok: "emerald", down: "red",
};

export default function AIProvidersPage() {
  const live = apiBaseConfigured();
  const [perms, setPerms] = useState<string[]>([]);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [usage, setUsage] = useState<AIUsage[]>([]);
  const [agents, setAgents] = useState<AgentRef[]>([]);
  const [health, setHealth] = useState<Record<string, { status: string; detail: string | null }>>({});
  const [code, setCode] = useState("openai");
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [assign, setAssign] = useState<Record<string, { p?: string; m?: string }>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const has = (p: string) => perms.includes("system_owner") || perms.includes(p);
  const reload = () => {
    aiProviderApi.list().then(setProviders).catch(() => undefined);
    aiProviderApi.usage().then(setUsage).catch(() => undefined);
    agentsList().then(setAgents).catch(() => undefined);
  };

  useEffect(() => {
    if (!live) return;
    me().then((u) => setPerms(u.permissions)).catch(() => undefined);
    reload();
  }, [live]);

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setErr(null); setMsg(null);
    try { await fn(); if (ok) setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  async function checkHealth(id: string) {
    setErr(null);
    try {
      const h = await aiProviderApi.health(id);
      setHealth({ ...health, [id]: { status: h.status, detail: h.detail } });
    } catch (e) { setErr((e as Error).message); }
  }

  async function saveAssignment(agentId: string) {
    const a = assign[agentId];
    if (!a?.p) { setErr("Выберите основного провайдера"); return; }
    await run(
      () => aiProviderApi.setAssignment(agentId, { primary_provider_id: a.p, primary_model: a.m || undefined }),
      "Модель назначена агенту",
    );
  }

  if (!live) {
    return (
      <>
        <PageHead title="ИИ-провайдеры" desc="Сменяемые поставщики ИИ" />
        <Card title="Backend не настроен"><p className="muted">Экран работает при подключённом backend.</p></Card>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="ИИ-провайдеры"
        desc="Сменяемые поставщики ИИ (OpenAI, Anthropic, Gemini, локальный). Реальные вызовы по умолчанию выключены (эхо-режим); ключи задаются в окружении и не хранятся в системе."
      />

      {(msg || err) && (
        <div className="alert" style={{ marginBottom: 12 }}>
          <div className="alert__icon">{err ? "⚠" : "✓"}</div>
          <div className="muted" style={{ fontSize: 13 }}>{err || msg}</div>
        </div>
      )}

      {has("ai.provider.manage") && (
        <Card title="Подключить провайдера" flush>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: 14, alignItems: "center" }}>
            <select className="input" value={code} onChange={(e) => setCode(e.target.value)}>
              {CODES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input className="input" placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} />
            <input className="input" placeholder="Модель по умолчанию" value={model} onChange={(e) => setModel(e.target.value)} />
            <button className="btn btn--primary btn--sm"
                    onClick={() => run(() => aiProviderApi.create({ code, name: name || code, default_model: model || undefined }), "Провайдер подключён")}>
              Подключить
            </button>
          </div>
        </Card>
      )}

      <div style={{ height: 12 }} />
      <Card title={`Провайдеры — ${providers.length}`} flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Код</th><th>Название</th><th>Модель</th><th>Ключ</th><th>Включён</th><th>Подключение</th><th>Действия</th></tr></thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.id}>
                  <td className="muted">{p.code}</td>
                  <td className="table__strong">{p.name}</td>
                  <td className="muted">{p.default_model || "—"}</td>
                  <td className="muted">{p.credentials_configured_externally ? p.key_hint : <Badge tone="amber">нет ключа</Badge>}</td>
                  <td>{p.enabled ? <Badge tone="emerald">да</Badge> : <Badge tone="gray">нет</Badge>}</td>
                  <td>{health[p.id] ? <Badge tone={HEALTH[health[p.id].status] || "gray"}>{health[p.id].status}</Badge> : "—"}</td>
                  <td>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {has("ai.provider.manage") && (
                        <>
                          <button className="btn btn--sm" onClick={() => run(() => aiProviderApi.setEnabled(p.id, !p.enabled))}>
                            {p.enabled ? "Выключить" : "Включить"}
                          </button>
                          <button className="btn btn--sm" onClick={() => checkHealth(p.id)}>Проверить</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {providers.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 16 }}>Провайдеры не подключены.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      {has("ai.provider.manage") && agents.length > 0 && (
        <>
          <div style={{ height: 12 }} />
          <Card title="Назначение модели агентам" flush className="span-2">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Агент</th><th>Провайдер</th><th>Модель</th><th></th></tr></thead>
                <tbody>
                  {agents.map((a) => (
                    <tr key={a.id}>
                      <td className="table__strong">{a.name}</td>
                      <td>
                        <select className="input" value={assign[a.id]?.p || ""}
                                onChange={(e) => setAssign({ ...assign, [a.id]: { ...assign[a.id], p: e.target.value } })}>
                          <option value="">—</option>
                          {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                      </td>
                      <td>
                        <input className="input" placeholder="модель" value={assign[a.id]?.m || ""}
                               onChange={(e) => setAssign({ ...assign, [a.id]: { ...assign[a.id], m: e.target.value } })} style={{ width: 140 }} />
                      </td>
                      <td><button className="btn btn--sm" onClick={() => saveAssignment(a.id)}>Назначить</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <div style={{ height: 12 }} />
      <Card title={`Расход ИИ — ${usage.length}`} flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Дата</th><th>Модель</th><th>Токены (вх/исх)</th><th>Стоимость</th><th>Запрос</th></tr></thead>
            <tbody>
              {usage.map((u) => (
                <tr key={u.id}>
                  <td className="muted">{new Date(u.created_at).toLocaleString("ru-RU")}</td>
                  <td className="muted">{u.model || "—"}</td>
                  <td className="muted">{u.tokens_in} / {u.tokens_out}</td>
                  <td className="muted">{u.cost.toFixed(4)}</td>
                  <td className="muted" style={{ fontSize: 11 }}>{u.request_id || "—"}</td>
                </tr>
              ))}
              {usage.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Записей расхода нет.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 12 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Ключи доступа задаются только через окружение и не хранятся в системе (в интерфейсе — маска).
          ИИ формирует только предложения и черновики; юридические, финансовые, кадровые, нормативные
          и внешние действия выполняются лишь уполномоченным человеком.
        </div>
      </div>
    </>
  );
}
