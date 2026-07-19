"use client";

/* «Заявки и выдача материалов» — рабочий контур (backend /procurement).
 * Заявка по проекту/объекту/задаче → согласование R2–R4 (+MFA для критических)
 * → резерв → выдача (в т. ч. частичная) → подтверждение получения → возврат.
 * Данные из backend, без mock; без backend — честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { apiBaseConfigured, me } from "../../../../lib/authApi";
import { coreApi, type Project } from "../../../../lib/coreApi";
import {
  materialsApi,
  type Warehouse,
  type MaterialRequest,
  type RequestDetail,
} from "../../../../lib/materialsApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  draft: "gray", submitted: "amber", pending_approval: "amber", approved: "navy",
  reserved: "navy", partially_issued: "navy", issued: "emerald", rejected: "red",
  closed: "emerald", cancelled: "red",
};

export default function MaterialFlowPage() {
  const live = apiBaseConfigured();
  const [projects, setProjects] = useState<Project[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [projectId, setProjectId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [empId, setEmpId] = useState<string | null>(null);
  const [requests, setRequests] = useState<MaterialRequest[]>([]);
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [lastIssue, setLastIssue] = useState<string | null>(null);
  const [desc, setDesc] = useState("");
  const [qty, setQty] = useState("");
  const [critical, setCritical] = useState(false);
  const [issueQty, setIssueQty] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!live) return;
    me().then((u) => setEmpId(u.employee_id)).catch(() => undefined);
    coreApi.listProjects().then((p) => { setProjects(p); if (p[0]) setProjectId(p[0].id); }).catch(() => undefined);
    materialsApi.listWarehouses().then((w) => { setWarehouses(w); if (w[0]) setWarehouseId(w[0].id); }).catch(() => undefined);
  }, [live]);

  const reload = () => {
    if (projectId) materialsApi.listRequests(projectId).then(setRequests).catch(() => undefined);
  };
  useEffect(reload, [projectId]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); if (detail) openDetail(detail.id); }
    catch (e) { setErr((e as Error).message); }
  }

  async function createRequest() {
    if (!projectId || !qty) return;
    await run(() => materialsApi.createRequest(projectId, {
      priority: critical ? "high" : "normal", is_critical: critical,
      lines: [{ description: desc || "Материал", quantity: Number(qty) }],
    }), "Заявка создана (черновик)");
    setDesc(""); setQty(""); setCritical(false);
  }
  function openDetail(id: string) { materialsApi.getRequest(id).then(setDetail).catch(() => undefined); }

  async function issueLine(lineId: string) {
    if (!detail || !warehouseId) return;
    const q = Number(issueQty[lineId]);
    if (!q) return;
    await run(async () => {
      const r = await materialsApi.issue(detail.id, {
        warehouse_id: warehouseId, issued_to: empId || undefined,
        items: [{ request_line_id: lineId, quantity: q }],
      });
      setLastIssue(r.id);
    }, "Выдача проведена");
    setIssueQty((s) => ({ ...s, [lineId]: "" }));
  }

  if (!live) {
    return (
      <>
        <PageHead title="Заявки и выдача материалов" desc="Заявка → согласование → резерв → выдача → подтверждение → возврат" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Заявки и выдача материалов"
        desc="Полный цикл по проекту/объекту/задаче · данные из backend"
        action={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select value={projectId} onChange={(e) => { setProjectId(e.target.value); setDetail(null); }} style={sel}>
              <option value="">— проект —</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)} style={sel}>
              <option value="">— склад —</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
        }
      />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <Card title="Заявки на материалы" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap", alignItems: "center" }}>
          <input placeholder="Материал / описание" value={desc} onChange={(e) => setDesc(e.target.value)} style={inp} />
          <input placeholder="Кол-во" value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" style={{ ...inp, maxWidth: 120 }} />
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <input type="checkbox" checked={critical} onChange={(e) => setCritical(e.target.checked)} /> критическая (R4+MFA)
          </label>
          <button className="btn btn--primary btn--sm" onClick={createRequest} disabled={!projectId}><Icons.plus width={16} height={16} /> Новая заявка</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>№</th><th>Позиций</th><th>Приоритет</th><th>Риск</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {requests.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Заявок нет.</td></tr>}
              {requests.map((r) => (
                <tr key={r.id} style={detail?.id === r.id ? { background: "var(--emerald-50)" } : undefined}>
                  <td className="table__strong">{r.number || r.id.slice(0, 8)}</td>
                  <td>{r.lines_count}</td>
                  <td>{r.priority}{r.is_critical ? " ⚠" : ""}</td>
                  <td><Risk level={r.risk_level as "R0" | "R1" | "R2" | "R3" | "R4"} /></td>
                  <td><Badge tone={ST[r.status] || "gray"}>{r.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {r.status === "draft" && <button className="btn btn--ghost btn--sm" onClick={() => run(() => materialsApi.requestApproval(r.id), "Отправлено на согласование")}>На согласование</button>}
                    {r.status === "pending_approval" && r.risk_level !== "R4" && <button className="btn btn--emerald btn--sm" onClick={() => run(() => materialsApi.decide(r.id, "approved"), "Заявка утверждена")}>Утвердить</button>}
                    {r.status === "pending_approval" && r.risk_level === "R4" && <span className="muted" style={{ fontSize: 12 }}>R4 — нужен MFA</span>}
                    {["approved", "reserved", "partially_issued"].includes(r.status) && warehouseId && <button className="btn btn--ghost btn--sm" onClick={() => run(() => materialsApi.reserve(r.id, warehouseId), "Остаток зарезервирован")}>Резерв</button>}
                    <button className="btn btn--ghost btn--sm" onClick={() => openDetail(r.id)}>Позиции</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {detail && (
        <>
          <div style={{ height: 18 }} />
          <Card title={`Позиции заявки ${detail.number || detail.id.slice(0, 8)} · ${detail.status}`} flush className="span-2">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Описание</th><th style={{ textAlign: "right" }}>Заявлено</th><th style={{ textAlign: "right" }}>Резерв</th><th style={{ textAlign: "right" }}>Выдано</th><th style={{ textAlign: "right" }}>Возврат</th><th>Выдать</th></tr></thead>
                <tbody>
                  {detail.lines.map((ln) => {
                    const canIssue = ["approved", "reserved", "partially_issued"].includes(detail.status) && ln.material_id;
                    return (
                      <tr key={ln.id}>
                        <td className="table__strong">{ln.description || ln.material_id?.slice(0, 8) || "—"}</td>
                        <td style={{ textAlign: "right" }}>{ln.quantity}</td>
                        <td style={{ textAlign: "right" }}>{ln.reserved_quantity}</td>
                        <td style={{ textAlign: "right" }}>{ln.issued_quantity}</td>
                        <td style={{ textAlign: "right" }}>{ln.returned_quantity}</td>
                        <td>
                          {canIssue ? (
                            <span style={{ display: "flex", gap: 6 }}>
                              <input value={issueQty[ln.id] || ""} onChange={(e) => setIssueQty((s) => ({ ...s, [ln.id]: e.target.value }))} inputMode="decimal" placeholder="кол-во" style={{ ...inp, maxWidth: 90 }} />
                              <button className="btn btn--emerald btn--sm" onClick={() => issueLine(ln.id)}>Выдать</button>
                            </span>
                          ) : !ln.material_id ? <span className="muted" style={{ fontSize: 12 }}>нет материала</span> : <span className="muted" style={{ fontSize: 12 }}>—</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {lastIssue && (
              <div style={{ padding: "10px 16px", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span className="muted" style={{ fontSize: 12 }}>Последняя выдача {lastIssue.slice(0, 8)}:</span>
                <button className="btn btn--emerald btn--sm" onClick={() => run(async () => { await materialsApi.acknowledge(lastIssue, true); setLastIssue(null); }, "Получение подтверждено")}>Подтвердить получение</button>
                <button className="btn btn--ghost btn--sm" onClick={() => run(async () => { await materialsApi.acknowledge(lastIssue, false, "расхождение"); setLastIssue(null); }, "Выдача оспорена")}>Оспорить</button>
              </div>
            )}
          </Card>
        </>
      )}

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Заявка связана с проектом, объектом и задачей. Согласование — R2, срочная — R3,
          критическая операция — R4 с подтверждением MFA. Резерв уменьшает свободный остаток;
          выдача может быть частичной и снимает резерв; получатель подтверждает получение;
          возврат приходует остаток обратно. Разделение ролей: инициатор (procurement.manage),
          согласующий (procurement.approve), склад (warehouse.manage). Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = {
  flex: 1, minWidth: 160, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)",
  borderRadius: 8, fontSize: 14,
};
const sel: React.CSSProperties = { padding: "8px 12px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
