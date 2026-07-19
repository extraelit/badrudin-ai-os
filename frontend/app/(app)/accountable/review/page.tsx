"use client";

/* Подотчётные средства — проверка бухгалтером (backend /accountable). Проверка
 * расходов, авансовых отчётов, возврат/возмещение. Данные из backend, без mock. */
import { useEffect, useState } from "react";
import { PageHead, Card, Badge } from "../../../../components/ui";
import { apiBaseConfigured } from "../../../../lib/authApi";
import { accountableApi, type Advance, type Expense } from "../../../../lib/accountableApi";

export default function AccountableReviewPage() {
  const live = apiBaseConfigured();
  const [advances, setAdvances] = useState<Advance[]>([]);
  const [sel, setSel] = useState("");
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const reload = () => accountableApi.listAdvances().then(setAdvances).catch(() => undefined);
  useEffect(() => { if (live) reload(); }, [live]);
  useEffect(() => { if (live && sel) accountableApi.listExpenses(sel).then(setExpenses).catch(() => undefined); else setExpenses([]); }, [live, sel]);

  async function verify(e: Expense, decision: "approved" | "rejected") {
    await accountableApi.verifyExpense(e.id, decision);
    accountableApi.listExpenses(sel).then(setExpenses); setMsg("Расход проверен");
  }
  async function settle(a: Advance) {
    if (a.status === "awaiting_return") await accountableApi.settle(a.id, "return", Number(a.balance_amount));
    if (a.status === "awaiting_reimbursement") await accountableApi.settle(a.id, "reimbursement", Number(a.amount_reimbursable));
    reload(); setMsg("Расчёт зафиксирован");
  }

  if (!live) {
    return (
      <>
        <PageHead title="Подотчётные средства — проверка" desc="Проверка расходов и авансовых отчётов" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Проверка подотчётных расходов"
        desc="Бухгалтер проверяет расходы и авансовые отчёты, фиксирует возврат/возмещение"
        action={
          <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)" }}>
            <option value="">— выдача —</option>
            {advances.map((a) => <option key={a.id} value={a.id}>{a.purpose} · {a.status}</option>)}
          </select>
        }
      />
      {msg && <div className="alert" style={{ marginBottom: 16 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}

      <Card title="Расходы к проверке" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Дата</th><th>Описание</th><th style={{ textAlign: "right" }}>Сумма</th><th>Чек</th><th>Статус</th><th>Решение</th></tr></thead>
            <tbody>
              {!sel && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Выберите выдачу.</td></tr>}
              {sel && expenses.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Расходов нет.</td></tr>}
              {expenses.map((e) => (
                <tr key={e.id}>
                  <td className="table__muted">{e.expense_date}</td>
                  <td className="table__strong">{e.description}</td>
                  <td style={{ textAlign: "right" }}>{e.amount}</td>
                  <td>{e.document_status === "missing" ? <Badge tone="red">нет</Badge> : <Badge tone="emerald">есть</Badge>}</td>
                  <td><Badge tone={e.verification_status === "approved" ? "emerald" : e.verification_status === "rejected" ? "red" : "amber"}>{e.verification_status}</Badge></td>
                  <td style={{ display: "flex", gap: 6 }}>
                    {e.verification_status === "submitted" && (
                      <>
                        <button className="btn btn--emerald btn--sm" onClick={() => verify(e, "approved")}>Принять</button>
                        <button className="btn btn--ghost btn--sm" onClick={() => verify(e, "rejected")}>Отклонить</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <Card title="Расчёты по выдачам (возврат / возмещение)" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Назначение</th><th style={{ textAlign: "right" }}>Выдано</th><th style={{ textAlign: "right" }}>Подтверждено</th><th style={{ textAlign: "right" }}>К возврату</th><th style={{ textAlign: "right" }}>К возмещению</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {advances.filter((a) => ["awaiting_return", "awaiting_reimbursement", "closed"].includes(a.status)).length === 0 &&
                <tr><td colSpan={7} className="muted" style={{ padding: 16 }}>Нет выдач к расчёту.</td></tr>}
              {advances.filter((a) => ["awaiting_return", "awaiting_reimbursement", "closed"].includes(a.status)).map((a) => (
                <tr key={a.id}>
                  <td className="table__strong">{a.purpose}</td>
                  <td style={{ textAlign: "right" }}>{a.amount_issued}</td>
                  <td style={{ textAlign: "right" }}>{a.amount_spent_confirmed}</td>
                  <td style={{ textAlign: "right" }}>{a.balance_amount}</td>
                  <td style={{ textAlign: "right" }}>{a.amount_reimbursable}</td>
                  <td><Badge tone={a.status === "closed" ? "emerald" : "amber"}>{a.status}</Badge></td>
                  <td>
                    {a.status === "awaiting_return" && <button className="btn btn--emerald btn--sm" onClick={() => settle(a)}>Зафиксировать возврат</button>}
                    {a.status === "awaiting_reimbursement" && <button className="btn btn--emerald btn--sm" onClick={() => settle(a)}>Зафиксировать возмещение</button>}
                    {a.status === "closed" && <span className="muted" style={{ fontSize: 12 }}>✓ закрыто</span>}
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
          Проверку выполняет бухгалтер (право <strong>accountable.account</strong>), отдельно от
          инициатора и согласующего. Возврат остатка и возмещение перерасхода только фиксируются —
          система не проводит банковских операций. Все решения — в журнале аудита.
        </div>
      </div>
    </>
  );
}
