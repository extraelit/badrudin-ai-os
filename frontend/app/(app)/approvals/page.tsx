"use client";

/* Согласования — рабочий контур (backend /core/approvals). Руководитель
 * утверждает или возвращает поручения и ежедневные отчёты (человек в контуре). */
import { useEffect, useState } from "react";
import { PageHead, Card, Badge } from "../../../components/ui";
import { apiBaseConfigured } from "../../../lib/authApi";
import { coreApi, type ApprovalItem } from "../../../lib/coreApi";

export default function ApprovalsPage() {
  const live = apiBaseConfigured();
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const reload = () => coreApi.listApprovals().then(setItems).catch(() => setMsg("Ошибка загрузки"));
  useEffect(() => { if (live) reload(); }, [live]);

  async function decide(a: ApprovalItem, decision: "approved" | "rejected") {
    await coreApi.decideApproval(a.id, decision);
    setMsg(decision === "approved" ? "Согласовано" : "Возвращено на доработку");
    reload();
  }

  if (!live) {
    return (
      <>
        <PageHead title="Согласования R0–R4" desc="Человек в контуре критических решений" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="Согласования" desc="Утверждение поручений и отчётов руководителем · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 16 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}

      <Card title="Ожидают решения" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Предмет</th><th>Тип</th><th>Статус</th><th>Решение</th></tr></thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Нет ожидающих согласований.</td></tr>}
              {items.map((a) => (
                <tr key={a.id}>
                  <td className="table__strong">{a.title || a.approval_type}</td>
                  <td>{a.entity_type === "task" ? "Поручение" : a.entity_type === "daily_report" ? "Ежедневный отчёт" : a.entity_type}</td>
                  <td><Badge tone="amber">{a.status}</Badge></td>
                  <td style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn--emerald btn--sm" onClick={() => decide(a, "approved")}>Утвердить</button>
                    <button className="btn btn--ghost btn--sm" onClick={() => decide(a, "rejected")}>Вернуть</button>
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
          Решение принимает уполномоченный человек (право <strong>approval.decide</strong>).
          Утверждение поручения переводит его в работу; утверждение отчёта фиксирует приёмку.
          Все решения записываются в журнал аудита.
        </div>
      </div>
    </>
  );
}
