"use client";

/* Подотчётные средства — рабочий контур (backend /accountable). Выдача под
 * отчёт, расходы с чеками, авансовый отчёт. Данные из backend, без mock. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge, Risk } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { apiBaseConfigured, me } from "../../../lib/authApi";
import { accountableApi, type Advance, type Expense, type Category, type AccSummary } from "../../../lib/accountableApi";

const ST: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  draft: "gray", pending_approval: "amber", approved: "navy", issued: "navy",
  partially_reported: "navy", under_accounting_review: "amber", awaiting_return: "amber",
  awaiting_reimbursement: "amber", closed: "emerald", cancelled: "red", overdue: "red",
};

export default function AccountablePage() {
  const live = apiBaseConfigured();
  const [sum, setSum] = useState<AccSummary | null>(null);
  const [advances, setAdvances] = useState<Advance[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [empId, setEmpId] = useState<string | null>(null);
  const [sel, setSel] = useState<string>("");
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [purpose, setPurpose] = useState("");
  const [amount, setAmount] = useState("");
  const [expAmount, setExpAmount] = useState("");
  const [expDesc, setExpDesc] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const reloadTop = () => {
    accountableApi.summary().then(setSum).catch(() => undefined);
    accountableApi.listAdvances().then(setAdvances).catch(() => undefined);
  };
  useEffect(() => {
    if (!live) return;
    me().then((u) => setEmpId(u.employee_id)).catch(() => undefined);
    accountableApi.listCategories().then(setCats).catch(() => undefined);
    reloadTop();
  }, [live]);
  useEffect(() => {
    if (live && sel) accountableApi.listExpenses(sel).then(setExpenses).catch(() => undefined);
    else setExpenses([]);
  }, [live, sel]);

  async function createAdvance() {
    if (!empId || !purpose.trim() || !amount) return;
    await accountableApi.createAdvance({ employee_id: empId, purpose: purpose.trim(), amount_issued: Number(amount) });
    setPurpose(""); setAmount(""); reloadTop(); setMsg("Выдача создана (черновик)");
  }
  async function adv(a: Advance, action: "request" | "decide" | "issue") {
    if (action === "request") await accountableApi.requestApproval(a.id);
    if (action === "decide") await accountableApi.decide(a.id, "approved");
    if (action === "issue") await accountableApi.issue(a.id);
    reloadTop();
  }
  async function addExpense() {
    if (!sel || !cats[0] || !expAmount) return;
    const e = await accountableApi.addExpense(sel, {
      expense_category_id: cats[0].id, amount: Number(expAmount),
      expense_date: new Date().toISOString().slice(0, 10), description: expDesc || "Расход",
    });
    await accountableApi.attachReceipt(e.id, { duplicate_hash: `R-${Date.now()}` });
    setExpAmount(""); setExpDesc(""); accountableApi.listExpenses(sel).then(setExpenses); setMsg("Расход добавлен с чеком");
  }
  async function report() {
    if (!sel) return;
    await accountableApi.submitReport(sel);
    reloadTop(); setMsg("Авансовый отчёт сформирован");
  }

  if (!live) {
    return (
      <>
        <PageHead title="Подотчётные средства" desc="Выдача, расходы, авансовые отчёты" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead title="Подотчётные средства" desc="Выдача под отчёт → расходы с чеками → авансовый отчёт · данные из backend" />
      {msg && <div className="alert" style={{ marginBottom: 16 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Открытые выдачи" value={String(sum?.advances_open ?? "—")} icon="finance" tone="navy" foot={`просрочено: ${sum?.advances_overdue ?? 0}`} />
        <Kpi label="Выдано" value={`${sum?.total_issued ?? "—"} ₽`} icon="finance" tone="navy" foot="всего" />
        <Kpi label="Подтверждено" value={`${sum?.total_spent ?? "—"} ₽`} icon="reports" tone="emerald" foot="расходы" />
        <Kpi label="К закрытию" value={`${sum?.total_outstanding ?? "—"} ₽`} icon="approvals" tone="amber" foot={`отчётов на проверке: ${sum?.reports_pending ?? 0}`} />
      </div>

      <Card title="Выдачи под отчёт" flush className="span-2">
        <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
          <input placeholder="Назначение" value={purpose} onChange={(e) => setPurpose(e.target.value)} style={inp} />
          <input placeholder="Сумма, ₽" value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" style={{ ...inp, maxWidth: 140 }} />
          <button className="btn btn--primary btn--sm" onClick={createAdvance}><Icons.plus width={16} height={16} /> Выдать под отчёт</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Назначение</th><th style={{ textAlign: "right" }}>Выдано</th><th style={{ textAlign: "right" }}>Остаток</th><th>Риск</th><th>Статус</th><th>Действие</th></tr></thead>
            <tbody>
              {advances.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Выдач нет.</td></tr>}
              {advances.map((a) => (
                <tr key={a.id} style={a.id === sel ? { background: "var(--emerald-50)" } : undefined}>
                  <td className="table__strong">{a.purpose}</td>
                  <td style={{ textAlign: "right" }}>{a.amount_issued}</td>
                  <td style={{ textAlign: "right" }}>{a.balance_amount}</td>
                  <td><Risk level={a.risk_level as "R0" | "R1" | "R2" | "R3" | "R4"} /></td>
                  <td><Badge tone={ST[a.status] || "gray"}>{a.status}</Badge></td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {a.status === "draft" && <button className="btn btn--ghost btn--sm" onClick={() => adv(a, "request")}>На согласование</button>}
                    {a.status === "pending_approval" && a.risk_level !== "R4" && <button className="btn btn--emerald btn--sm" onClick={() => adv(a, "decide")}>Утвердить</button>}
                    {a.status === "pending_approval" && a.risk_level === "R4" && <span className="muted" style={{ fontSize: 12 }}>R4 — MFA</span>}
                    {a.status === "approved" && <button className="btn btn--emerald btn--sm" onClick={() => adv(a, "issue")}>Выдать</button>}
                    {(a.status === "issued" || a.status === "partially_reported") && <button className="btn btn--ghost btn--sm" onClick={() => setSel(a.id)}>Расходы</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {sel && (
        <>
          <div style={{ height: 18 }} />
          <Card title="Расходы по выданной сумме" flush className="span-2">
            <div style={{ display: "flex", gap: 10, padding: "12px 16px", flexWrap: "wrap" }}>
              <input placeholder="Сумма расхода, ₽" value={expAmount} onChange={(e) => setExpAmount(e.target.value)} inputMode="decimal" style={{ ...inp, maxWidth: 160 }} />
              <input placeholder="Что оплачено" value={expDesc} onChange={(e) => setExpDesc(e.target.value)} style={inp} />
              <button className="btn btn--primary btn--sm" onClick={addExpense}>Добавить расход + чек</button>
              <button className="btn btn--emerald btn--sm" onClick={report}>Сформировать авансовый отчёт</button>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Дата</th><th>Описание</th><th style={{ textAlign: "right" }}>Сумма</th><th>Чек</th><th>Проверка</th></tr></thead>
                <tbody>
                  {expenses.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Расходов нет.</td></tr>}
                  {expenses.map((e) => (
                    <tr key={e.id}>
                      <td className="table__muted">{e.expense_date}</td>
                      <td className="table__strong">{e.description}</td>
                      <td style={{ textAlign: "right" }}>{e.amount}</td>
                      <td>{e.document_status === "missing" ? <Badge tone="red">нет</Badge> : <Badge tone="emerald">есть</Badge>}</td>
                      <td><Badge tone={e.verification_status === "approved" ? "emerald" : e.verification_status === "rejected" ? "red" : "amber"}>{e.verification_status}</Badge></td>
                    </tr>
                  ))}
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
          Выдача согласуется человеком (R3, крупная — R4 + MFA). Расход требует подтверждающего
          документа; один чек нельзя использовать повторно. Проверку расходов и авансового отчёта
          выполняет бухгалтер (экран «Проверка»). Система не проводит платежей: возврат и
          возмещение только фиксируются. Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const inp: React.CSSProperties = {
  flex: 1, minWidth: 180, padding: "8px 12px", border: "1px solid var(--line, #e2e8f0)",
  borderRadius: 8, fontSize: 14,
};
