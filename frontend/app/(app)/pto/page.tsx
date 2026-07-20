"use client";

/* «Исполнительная документация ПТО» (backend /pto). Реестр исполнительной
 * документации объекта с версионированием и инженерным согласованием; контроль
 * обязательного комплекта. Данные из backend, без mock; без backend — честное
 * пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured } from "../../../lib/authApi";
import { coreApi, type Project } from "../../../lib/coreApi";
import {
  ptoApi,
  type Completeness,
  type ExecutiveDocument,
  type PtoSummary,
} from "../../../lib/ptoApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  draft: "gray", rejected: "red", under_review: "amber", approved: "emerald", superseded: "gray",
};
const TYPES = ["hidden_work_act", "as_built_scheme", "work_log", "material_certificate", "lab_report", "cumulative_statement", "other"];
const TYPE_RU: Record<string, string> = {
  hidden_work_act: "акт скрытых работ", as_built_scheme: "исполнительная схема",
  work_log: "журнал работ", material_certificate: "сертификат материала",
  lab_report: "лабораторный документ", cumulative_statement: "накопительная ведомость", other: "прочее",
};

export default function PtoPage() {
  const live = apiBaseConfigured();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [sum, setSum] = useState<PtoSummary | null>(null);
  const [docs, setDocs] = useState<ExecutiveDocument[]>([]);
  const [comp, setComp] = useState<Completeness | null>(null);
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("hidden_work_act");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!live) return;
    coreApi.listProjects().then((p) => { setProjects(p); if (p[0]) setProjectId(p[0].id); }).catch(() => undefined);
    ptoApi.summary().then(setSum).catch(() => undefined);
  }, [live]);

  useEffect(() => {
    if (!live || !projectId) return;
    ptoApi.listDocuments(projectId).then(setDocs).catch(() => undefined);
    ptoApi.completeness(projectId).then(setComp).catch(() => undefined);
  }, [live, projectId]);

  const reload = () => {
    ptoApi.summary().then(setSum).catch(() => undefined);
    if (projectId) {
      ptoApi.listDocuments(projectId).then(setDocs).catch(() => undefined);
      ptoApi.completeness(projectId).then(setComp).catch(() => undefined);
    }
  };

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Исполнительная документация ПТО" desc="Реестр исполнительной документации, версии и обязательный комплект" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="Исполнительная документация ПТО" desc="Версионирование, инженерное согласование и контроль обязательного комплекта · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Документов" value={String(sum?.documents_total ?? "—")} icon="documents" tone="navy" foot={`утверждено: ${sum?.documents_approved ?? 0}`} />
        <Kpi label="Черновики" value={String(sum?.documents_draft ?? "—")} icon="documents" tone="gray" foot="на доработке" />
        <Kpi label="На согласовании" value={String(sum?.documents_under_review ?? "—")} icon="approvals" tone={sum && sum.documents_under_review ? "amber" : "emerald"} foot="у инженера" />
        <Kpi label="Устаревшие" value={String(sum?.documents_superseded ?? "—")} icon="reports" tone="gray" foot="заменены версиями" />
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        <span className="muted" style={{ fontSize: 13 }}>Объект:</span>
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)} style={sel}>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        {comp && (
          <Badge tone={comp.complete ? "emerald" : "amber"}>
            комплект: {comp.present.length}/{comp.required.length}{comp.complete ? " — полный" : ""}
          </Badge>
        )}
        {comp && comp.missing.length > 0 && (
          <span className="muted" style={{ fontSize: 12 }}>не хватает: {comp.missing.map((t) => TYPE_RU[t] || t).join(", ")}</span>
        )}
      </div>

      <Card title="Документы объекта" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <select value={docType} onChange={(e) => setDocType(e.target.value)} style={sel}>
            {TYPES.map((t) => <option key={t} value={t}>{TYPE_RU[t]}</option>)}
          </select>
          <input placeholder="Наименование документа" value={title} onChange={(e) => setTitle(e.target.value)} style={inp} />
          <button className="btn btn--primary btn--sm" onClick={() => { if (title && projectId) { run(() => ptoApi.createDocument({ project_id: projectId, doc_type: docType, title }), "Документ создан (приложите файл перед согласованием)"); setTitle(""); } }}><Icons.plus width={16} height={16} /> Добавить</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Тип</th><th>Наименование</th><th>Версия</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {docs.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Документов нет.</td></tr>}
              {docs.map((d) => (
                <tr key={d.id}>
                  <td className="table__muted">{TYPE_RU[d.doc_type] || d.doc_type}</td>
                  <td className="table__strong">{d.title}{d.number ? ` (№${d.number})` : ""}</td>
                  <td>v{d.version_number}</td>
                  <td><Badge tone={ST[d.status] || "gray"}>{d.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {(d.status === "draft" || d.status === "rejected") && d.file_id &&
                      <button className="btn btn--ghost btn--sm" onClick={() => run(() => ptoApi.submit(d.id), "Отправлено на согласование")}>На согласование</button>}
                    {(d.status === "draft" || d.status === "rejected") && !d.file_id &&
                      <span className="muted" style={{ fontSize: 12 }}>нужен файл</span>}
                    {d.status === "under_review" && (
                      <>
                        <button className="btn btn--emerald btn--sm" onClick={() => run(() => ptoApi.decide(d.id, "approved"), "Документ утверждён")}>Утвердить</button>
                        <button className="btn btn--ghost btn--sm" onClick={() => { const c = prompt("Замечание:") || undefined; run(() => ptoApi.decide(d.id, "rejected", c), "Отклонено"); }}>Отклонить</button>
                      </>
                    )}
                    {d.status === "approved" && <span className="muted" style={{ fontSize: 12 }}>✓ утверждён</span>}
                    {d.status === "superseded" && <span className="muted" style={{ fontSize: 12 }}>заменён новой версией</span>}
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
          Каждый документ версионируется: новая версия помечает предыдущую как
          «устаревшая». Утверждение выполняет <strong>уполномоченный инженер</strong> —
          ИИ не подменяет инженерную подпись (§12). Обязательный комплект контролируется
          автоматически. Доступ: <strong>pto.view</strong> / <strong>pto.manage</strong> /
          <strong> pto.approve</strong>. Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = { flex: 1, minWidth: 200, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)", borderRadius: 8, fontSize: 14 };
const sel: React.CSSProperties = { padding: "8px 10px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
