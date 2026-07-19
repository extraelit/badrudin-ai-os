"use client";

/* Панель директора — живая сводка рабочего ядра (backend /core/dashboard). */
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHead, Kpi, Card, Badge } from "../../../components/ui";
import { apiBaseConfigured } from "../../../lib/authApi";
import { coreApi, type Dashboard, type Project, type ApprovalItem } from "../../../lib/coreApi";

export default function DashboardPage() {
  const live = apiBaseConfigured();
  const [d, setD] = useState<Dashboard | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!live) return;
    Promise.all([coreApi.dashboard(), coreApi.listProjects(), coreApi.listApprovals()])
      .then(([dash, pr, ap]) => { setD(dash); setProjects(pr); setApprovals(ap); })
      .catch(() => setErr("Не удалось загрузить данные. Проверьте вход и доступность backend."));
  }, [live]);

  if (!live) {
    return (
      <>
        <PageHead title="Панель генерального директора" desc="Единый центр управления" />
        <div className="alert"><div className="alert__icon">ℹ</div>
          <div className="muted" style={{ fontSize: 13 }}>
            Backend не подключён (NEXT_PUBLIC_API_BASE_URL не задан). Это рабочий контур —
            данные загружаются из backend после входа. Демо-данные здесь не показываются.
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Панель генерального директора"
        desc="Живая сводка · данные из backend"
        action={<Link href="/sites" className="btn btn--primary btn--sm">Объекты и проекты</Link>}
      />
      {err && <div className="alert" style={{ marginBottom: 16 }}><div className="alert__icon">!</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Проекты" value={String(d?.projects ?? "—")} icon="sites" tone="navy" foot="доступные" />
        <Kpi label="Объекты" value={String(d?.sites ?? "—")} icon="sites" tone="navy" foot="площадки" />
        <Kpi label="Задачи в работе" value={String(d?.tasks_open ?? "—")} icon="tasks" tone="emerald" foot={`просрочено: ${d?.tasks_overdue ?? 0}`} />
        <Kpi label="Ждут согласования" value={String(d?.approvals_pending ?? "—")} icon="approvals" tone="amber" foot={`отчётов сегодня: ${d?.reports_today ?? 0}`} />
      </div>

      <div className="grid grid--2">
        <Card title="Проекты" flush>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Проект</th><th>Тип</th><th>Готовность</th><th>Статус</th></tr></thead>
              <tbody>
                {projects.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Проектов нет. Создайте на экране «Объекты и проекты».</td></tr>}
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td className="table__strong"><Link href="/sites" style={{ color: "var(--navy-600)" }}>{p.name}</Link></td>
                    <td className="table__muted">{p.project_type}</td>
                    <td>{p.completion_percent}%</td>
                    <td><Badge tone="emerald">{p.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Ждут вашего согласования" flush>
          <div className="list">
            {approvals.length === 0 && <div className="muted" style={{ padding: 16 }}>Нет ожидающих согласований.</div>}
            {approvals.map((a) => (
              <div key={a.id} className="list__item">
                <div className="list__main">
                  <div className="list__title">{a.title || a.approval_type}</div>
                  <div className="list__sub">{a.entity_type === "task" ? "Поручение" : a.entity_type === "daily_report" ? "Ежедневный отчёт" : a.entity_type}</div>
                </div>
                <Link href="/approvals" className="btn btn--ghost btn--sm">Открыть</Link>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}
