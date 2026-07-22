"use client";

/* «Панель руководителя» — сводка процессного ядра (backend /manager). Процессы по
 * статусам, просрочки, ожидающие согласования, запросы исключений по доказательствам,
 * проверки качества без решения; эскалация просроченных процессов (внутренние
 * уведомления). Всё ограничено доступными проектами; проверки прав — на сервере. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { apiBaseConfigured, me } from "../../../lib/authApi";
import {
  processApi,
  type ManagerOverview,
  type OverdueItem,
  type ExceptionItem,
} from "../../../lib/processApi";

export default function ManagerPage() {
  const live = apiBaseConfigured();
  const [perms, setPerms] = useState<string[]>([]);
  const [ov, setOv] = useState<ManagerOverview | null>(null);
  const [overdue, setOverdue] = useState<OverdueItem[]>([]);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const has = (p: string) => perms.includes("system_owner") || perms.includes(p);

  useEffect(() => {
    if (!live) return;
    me().then((u) => setPerms(u.permissions)).catch(() => undefined);
    processApi.managerOverview().then(setOv).catch(() => undefined);
    processApi.overdue().then(setOverdue).catch(() => undefined);
    processApi.exceptions().then(setExceptions).catch(() => undefined);
  }, [live]);

  async function escalate() {
    try {
      const r = await processApi.escalateOverdue();
      setMsg(`Создано уведомлений: ${r.notifications_created}`);
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Панель руководителя" desc="Сводка процессного ядра" />
        <Card title="Backend не настроен">
          <p className="muted">Экран работает при подключённом backend.</p>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Панель руководителя"
        desc="Процессы, просрочки, согласования, запросы исключений и качество по доступным проектам"
        action={
          has("management.view")
            ? <button className="btn btn--primary btn--sm" onClick={escalate}>Эскалировать просрочки</button>
            : undefined
        }
      />

      {msg && (
        <div className="alert" style={{ marginBottom: 14 }}>
          <div className="alert__icon">✓</div>
          <div className="muted" style={{ fontSize: 13 }}>{msg}</div>
        </div>
      )}

      {ov && (
        <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
          <Kpi label="Всего процессов" value={String(ov.processes_total)} icon="tasks" tone="navy" />
          <Kpi label="Просрочено" value={String(ov.overdue)} icon="approvals" tone={ov.overdue ? "red" : "emerald"} />
          <Kpi label="Ждут согласования" value={String(ov.pending_approval)} icon="approvals" tone="amber" />
          <Kpi label="На проверке" value={String(ov.submitted_for_review)} icon="documents" tone="navy" />
          <Kpi label="Запросы исключений" value={String(ov.evidence_exceptions_pending)} icon="documents" tone={ov.evidence_exceptions_pending ? "amber" : "navy"} />
          <Kpi label="Качество: без решения" value={String(ov.quality_pending_finalization)} icon="reports" tone="navy" />
        </div>
      )}

      <div className="grid grid--2">
        <Card title={`Просроченные процессы — ${overdue.length}`} flush>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Процесс</th><th>Вид</th><th>Риск</th><th>Срок</th></tr></thead>
              <tbody>
                {overdue.map((p) => (
                  <tr key={p.id}>
                    <td className="table__strong">{p.title}</td>
                    <td className="muted">{p.process_kind}</td>
                    <td><Badge tone={p.risk_level === "R4" || p.risk_level === "R3" ? "red" : "navy"}>{p.risk_level}</Badge></td>
                    <td className="muted">{p.due_at ? new Date(p.due_at).toLocaleDateString("ru-RU") : "—"}</td>
                  </tr>
                ))}
                {overdue.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Просрочек нет.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title={`Запросы исключений — ${exceptions.length}`} flush>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Тип доказательства</th><th>Причина</th><th>Статус</th></tr></thead>
              <tbody>
                {exceptions.map((x) => (
                  <tr key={x.id}>
                    <td className="table__strong">{x.evidence_type}</td>
                    <td className="muted">{x.reason}</td>
                    <td><Badge tone="amber">{x.status}</Badge></td>
                  </tr>
                ))}
                {exceptions.length === 0 && <tr><td colSpan={3} className="muted" style={{ padding: 16 }}>Ожидающих исключений нет.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
