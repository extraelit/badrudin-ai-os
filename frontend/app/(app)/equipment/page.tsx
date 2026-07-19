"use client";

/* «Техника, транспорт и инструмент» — рабочий контур (backend /equipment).
 * Реестр техники, назначение/возврат, эксплуатация (моточасы/пробег/простой),
 * техобслуживание с блокировкой выдачи, инструмент выдача/возврат. Данные из
 * backend, без mock; без backend — честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured, me } from "../../../lib/authApi";
import { coreApi, type Project } from "../../../lib/coreApi";
import {
  equipmentApi,
  type Equipment,
  type Tool,
  type Maintenance,
  type EquipmentSummary,
} from "../../../lib/equipmentApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  available: "emerald", assigned: "navy", in_use: "navy", under_repair: "red",
  under_inspection: "amber", idle: "gray", written_off: "gray",
  issued: "navy", returned: "emerald", ok: "emerald", worn: "amber", damaged: "red",
};

export default function EquipmentPage() {
  const live = apiBaseConfigured();
  const [sum, setSum] = useState<EquipmentSummary | null>(null);
  const [items, setItems] = useState<Equipment[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [maint, setMaint] = useState<Maintenance[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [empId, setEmpId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [toolName, setToolName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    equipmentApi.summary().then(setSum).catch(() => undefined);
    equipmentApi.list().then(setItems).catch(() => undefined);
    equipmentApi.listTools().then(setTools).catch(() => undefined);
    equipmentApi.listMaintenance().then(setMaint).catch(() => undefined);
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
        <PageHead title="Техника, транспорт и инструмент" desc="Реестр, назначение, эксплуатация, ТО, инструмент" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Техника, транспорт и инструмент"
        desc="Реестр, назначение на объект, эксплуатация, техобслуживание · данные из backend"
        action={
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} style={sel}>
            <option value="">— проект для выдачи —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        }
      />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Единиц техники" value={String(sum?.equipment_total ?? "—")} icon="procurement" tone="navy" foot={`доступно: ${sum?.equipment_available ?? 0}`} />
        <Kpi label="В работе" value={String(sum?.equipment_assigned ?? "—")} icon="sites" tone="navy" foot="назначено на объекты" />
        <Kpi label="В ремонте" value={String(sum?.equipment_under_repair ?? "—")} icon="approvals" tone={sum && sum.equipment_under_repair ? "amber" : "emerald"} foot={`заказов ТО: ${sum?.maintenance_open ?? 0}`} />
        <Kpi label="Инструмент выдан" value={`${sum?.tools_issued ?? "—"}/${sum?.tools_total ?? 0}`} icon="documents" tone="navy" foot={`ТО по сроку: ${sum?.service_due ?? 0}`} />
      </div>

      <Card title="Реестр техники" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Наименование техники" value={name} onChange={(e) => setName(e.target.value)} style={inp} />
          <button className="btn btn--primary btn--sm" onClick={() => { if (name) { run(() => equipmentApi.register({ name }), "Техника добавлена"); setName(""); } }}><Icons.plus width={16} height={16} /> В реестр</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Наименование</th><th>Тип</th><th>Статус</th><th style={{ textAlign: "right" }}>Моточасы</th><th style={{ textAlign: "right" }}>Пробег</th><th>Действие</th></tr></thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Техники нет.</td></tr>}
              {items.map((e) => (
                <tr key={e.id}>
                  <td className="table__strong">{e.name}</td>
                  <td className="table__muted">{e.asset_type}</td>
                  <td><Badge tone={ST[e.current_status] || "gray"}>{e.current_status}</Badge></td>
                  <td style={{ textAlign: "right" }}>{e.engine_hours}</td>
                  <td style={{ textAlign: "right" }}>{e.odometer_value}</td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {e.current_status === "available" && projectId && <button className="btn btn--emerald btn--sm" onClick={() => run(() => equipmentApi.assign(e.id, { project_id: projectId, responsible_employee_id: empId || undefined }), "Техника назначена")}>Выдать</button>}
                    {["assigned", "in_use"].includes(e.current_status) && <button className="btn btn--ghost btn--sm" onClick={() => run(() => equipmentApi.returnEquipment(e.id), "Техника возвращена")}>Вернуть</button>}
                    {["assigned", "in_use"].includes(e.current_status) && <button className="btn btn--ghost btn--sm" onClick={() => { const h = Number(prompt("Моточасы (итог):", e.engine_hours)); if (h) run(() => equipmentApi.logUsage(e.id, { usage_date: new Date().toISOString().slice(0, 10), engine_hours_end: h }), "Эксплуатация учтена"); }}>Смена</button>}
                    {e.current_status !== "under_repair" && e.current_status !== "written_off" && <button className="btn btn--ghost btn--sm" onClick={() => { const p = prompt("Проблема / вид ремонта:"); if (p) run(() => equipmentApi.openMaintenance({ asset_type: "equipment", asset_id: e.id, maintenance_type: "repair", problem_description: p }), "Заказ ТО создан"); }}>В ремонт</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Техобслуживание и ремонт" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Актив</th><th>Вид</th><th>Статус</th><th>Приоритет</th><th style={{ textAlign: "right" }}>Стоимость</th><th>Действие</th></tr></thead>
            <tbody>
              {maint.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Заказов ТО нет.</td></tr>}
              {maint.map((m) => (
                <tr key={m.id}>
                  <td className="table__muted">{m.asset_type} · {m.asset_id.slice(0, 8)}</td>
                  <td>{m.maintenance_type}</td>
                  <td><Badge tone={m.status === "completed" ? "emerald" : "amber"}>{m.status}</Badge></td>
                  <td>{m.priority}</td>
                  <td style={{ textAlign: "right" }}>{m.actual_cost ?? "—"}</td>
                  <td>{["open", "in_progress"].includes(m.status) && <button className="btn btn--emerald btn--sm" onClick={() => { const c = Number(prompt("Фактическая стоимость, ₽:", "0")); run(() => equipmentApi.completeMaintenance(m.id, { actual_cost: c || undefined }), "Ремонт завершён"); }}>Завершить</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Инструмент" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Наименование инструмента" value={toolName} onChange={(e) => setToolName(e.target.value)} style={inp} />
          <button className="btn btn--primary btn--sm" onClick={() => { if (toolName) { run(() => equipmentApi.registerTool({ name: toolName }), "Инструмент добавлен"); setToolName(""); } }}>В реестр</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Наименование</th><th>Тип</th><th>Статус</th><th>Состояние</th><th>Действие</th></tr></thead>
            <tbody>
              {tools.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Инструмента нет.</td></tr>}
              {tools.map((t) => (
                <tr key={t.id}>
                  <td className="table__strong">{t.name}</td>
                  <td className="table__muted">{t.tool_type || "—"}</td>
                  <td><Badge tone={ST[t.current_status] || "gray"}>{t.current_status}</Badge></td>
                  <td><Badge tone={ST[t.condition_status] || "gray"}>{t.condition_status}</Badge></td>
                  <td style={{ display: "flex", gap: 6 }}>
                    {t.current_status === "available" && empId && <button className="btn btn--emerald btn--sm" onClick={() => run(() => equipmentApi.issueTool(t.id, { employee_id: empId, project_id: projectId || undefined, condition_at_issue: "ok" }), "Инструмент выдан")}>Выдать</button>}
                    {["issued", "in_use"].includes(t.current_status) && <button className="btn btn--ghost btn--sm" onClick={() => { const c = prompt("Состояние при возврате (ok/worn/damaged):", "ok"); run(() => equipmentApi.returnTool(t.id, { condition_at_return: c || "ok" }), "Инструмент возвращён"); }}>Вернуть</button>}
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
          Единая модель: транспорт — категория техники (тип), инструмент ведётся отдельно. Техника с
          открытым заказом на ремонт или не прошедшая осмотр не выдаётся. Моточасы и пробег не
          уменьшаются. Доступ: <strong>equipment.view</strong> (реестр), <strong>equipment.manage</strong>
          (выдача, эксплуатация, инструмент), <strong>equipment.maintain</strong> (ремонт). Доступ к
          единице — через её проект. Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 180, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
const sel: React.CSSProperties = { padding: "8px 12px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
