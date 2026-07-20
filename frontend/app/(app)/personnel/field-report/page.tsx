"use client";

/* «Мобильный ежедневный отчёт прораба» — рабочий контур (backend /field-reports).
 * Составление отчёта по объекту: работы и объёмы, численность, техника, проблемы,
 * фото-доказательства; отправка и проверка руководителем. Данные из backend, без
 * mock; без backend — честное пустое состояние. Адаптивно для телефона. */
import { useEffect, useRef, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { apiBaseConfigured } from "../../../../lib/authApi";
import { coreApi, type Project } from "../../../../lib/coreApi";
import {
  fieldReportApi,
  type Report,
  type ReportDetail,
  type ReportSummary,
} from "../../../../lib/fieldReportApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  draft: "gray", submitted: "amber", correction_required: "red", approved: "emerald", rejected: "red",
};

export default function FieldReportPage() {
  const live = apiBaseConfigured();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [sum, setSum] = useState<ReportSummary | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [work, setWork] = useState("");
  const [qty, setQty] = useState("");
  const [prof, setProf] = useState("");
  const [profN, setProfN] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!live) return;
    coreApi.listProjects().then((p) => { setProjects(p); if (p[0]) setProjectId(p[0].id); }).catch(() => undefined);
    fieldReportApi.summary().then(setSum).catch(() => undefined);
  }, [live]);

  const reloadList = () => {
    if (projectId) fieldReportApi.list(projectId).then(setReports).catch(() => undefined);
    fieldReportApi.summary().then(setSum).catch(() => undefined);
  };
  useEffect(reloadList, [projectId]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reloadList(); if (detail) fieldReportApi.get(detail.id).then(setDetail); }
    catch (e) { setErr((e as Error).message); }
  }
  function open(id: string) { fieldReportApi.get(id).then(setDetail).catch(() => undefined); }

  async function createReport() {
    if (!projectId) return;
    // уникальный ключ на отправку: при нестабильной связи повтор не создаёт дубль (§18)
    const clientRequestId =
      (globalThis.crypto?.randomUUID?.() ?? `req-${Date.now()}-${Math.random().toString(36).slice(2)}`);
    await run(async () => {
      const r = await fieldReportApi.create(projectId, {
        report_date: new Date().toISOString().slice(0, 10), summary: "Смена",
        client_request_id: clientRequestId,
      });
      open(r.id);
    }, "Отчёт создан (черновик)");
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !detail) return;
    const buf = await f.arrayBuffer();
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
    await run(() => fieldReportApi.addEvidence(detail.id, { original_name: f.name, mime_type: f.type || "image/jpeg", content_base64: b64, kind: "photo" }), "Фото прикреплено");
    if (fileRef.current) fileRef.current.value = "";
  }

  if (!live) {
    return (
      <>
        <PageHead title="Ежедневный отчёт прораба" desc="Мобильная форма: работы, люди, техника, проблемы, фото" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  const editable = detail && ["draft", "correction_required"].includes(detail.status);

  return (
    <>
      <PageHead
        title="Ежедневный отчёт прораба"
        desc="Мобильная форма отчёта по объекту · данные из backend"
        action={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select value={projectId} onChange={(e) => { setProjectId(e.target.value); setDetail(null); }} style={sel}>
              <option value="">— проект —</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <button className="btn btn--primary btn--sm" onClick={createReport} disabled={!projectId}><Icons.plus width={16} height={16} /> Новый отчёт</button>
          </div>
        }
      />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Черновики" value={String(sum?.draft ?? "—")} icon="documents" tone="navy" foot="в работе" />
        <Kpi label="На проверке" value={String(sum?.submitted ?? "—")} icon="approvals" tone="amber" foot="ждут ПТО" />
        <Kpi label="На доработку" value={String(sum?.correction_required ?? "—")} icon="reports" tone={sum && sum.correction_required > 0 ? "amber" : "emerald"} foot="возвращены" />
        <Kpi label="Утверждены" value={String(sum?.approved ?? "—")} icon="reports" tone="emerald" foot="приняты" />
      </div>

      <Card title="Мои отчёты по объекту" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Дата</th><th>Статус</th><th>Комментарий ПТО</th><th>Действие</th></tr></thead>
            <tbody>
              {reports.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Отчётов нет.</td></tr>}
              {reports.map((r) => (
                <tr key={r.id} style={detail?.id === r.id ? { background: "var(--emerald-50)" } : undefined}>
                  <td className="table__strong">{r.report_date}</td>
                  <td><Badge tone={ST[r.status] || "gray"}>{r.status}</Badge></td>
                  <td className="table__muted">{r.review_comment || "—"}</td>
                  <td><button className="btn btn--ghost btn--sm" onClick={() => open(r.id)}>Открыть</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {detail && (
        <>
          <div style={{ height: 18 }} />
          <Card title={`Отчёт ${detail.report_date} · ${detail.status}`} flush className="span-2">
            {editable && (
              <div style={{ display: "grid", gap: 10, padding: "12px 16px" }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <input placeholder="Выполненная работа" value={work} onChange={(e) => setWork(e.target.value)} style={inp} />
                  <input placeholder="Объём" value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" style={{ ...inp, maxWidth: 110 }} />
                  <button className="btn btn--ghost btn--sm" onClick={() => { if (work && qty) { run(() => fieldReportApi.addWorkItem(detail.id, { work_type: work, actual_quantity: Number(qty) }), "Работа добавлена"); setWork(""); setQty(""); } }}>+ Работа</button>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <input placeholder="Профессия" value={prof} onChange={(e) => setProf(e.target.value)} style={inp} />
                  <input placeholder="Кол-во" value={profN} onChange={(e) => setProfN(e.target.value)} inputMode="numeric" style={{ ...inp, maxWidth: 110 }} />
                  <button className="btn btn--ghost btn--sm" onClick={() => { if (prof && profN) { run(() => fieldReportApi.addHeadcount(detail.id, { profession: prof, count: Number(profN) }), "Люди добавлены"); setProf(""); setProfN(""); } }}>+ Люди</button>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <input ref={fileRef} type="file" accept="image/*" onChange={onFile} style={{ fontSize: 13 }} />
                  <button className="btn btn--emerald btn--sm" onClick={() => run(() => fieldReportApi.submit(detail.id), "Отчёт отправлен на проверку")}>Отправить на проверку</button>
                </div>
              </div>
            )}
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Раздел</th><th>Содержимое</th></tr></thead>
                <tbody>
                  <tr><td className="table__strong">Работы</td><td>{detail.work_items.map((w) => `${w.work_type || "—"}: ${w.actual_quantity}`).join("; ") || "—"}</td></tr>
                  <tr><td className="table__strong">Люди</td><td>{detail.headcount.map((h) => `${h.profession}: ${h.count}`).join("; ") || "—"}</td></tr>
                  <tr><td className="table__strong">Техника</td><td>{detail.equipment.map((e) => `${e.name} (${e.hours} ч)`).join("; ") || "—"}</td></tr>
                  <tr><td className="table__strong">Проблемы</td><td>{detail.issues.map((i) => `${i.issue_type}: ${i.description}`).join("; ") || "—"}</td></tr>
                  <tr><td className="table__strong">Фото</td><td>{detail.evidence.length ? `${detail.evidence.length} шт. (${detail.evidence.map((e) => e.original_name).filter(Boolean).join(", ")})` : "—"}</td></tr>
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Отчёт составляет прораб (право <strong>daily_report.manage</strong>) по своему объекту:
          выполненные работы и объёмы (со связью с задачами), численность, техника, проблемы и риски,
          фото/файлы-доказательства (сохраняются в защищённом хранилище с проверкой типа и размера).
          После отправки правки закрыты. Проверку выполняет руководитель/ПТО (право
          <strong> daily_report.approve</strong>): утвердить, отклонить или вернуть на доработку.
          Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 150, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
const sel: React.CSSProperties = { padding: "8px 12px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
