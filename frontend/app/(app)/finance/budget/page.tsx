/* Модуль «Финансы и бюджеты». Экран 2 — бюджет проекта и статьи. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { budget, budgetLines } from "../../../../lib/finance";

export default function BudgetPage() {
  return (
    <>
      <PageHead
        title="Бюджет проекта"
        desc="Базовый бюджет формируется из утверждённой сметы; ручные статьи — только для расходов вне сметы"
        action={<button className="btn btn--ghost btn--sm"><Icons.plus width={16} height={16} /> Ручная статья</button>}
      />

      <Card
        title={budget.name}
        more={`v${budget.version}`}
        flush
        className="span-2"
      >
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", padding: "14px 16px 0" }}>
          <div><div className="muted" style={{ fontSize: 12 }}>Статус</div><Badge tone={budget.statusTone}>{budget.status}</Badge></div>
          <div><div className="muted" style={{ fontSize: 12 }}>План</div><div className="table__strong">{budget.plannedTotal} ₽</div></div>
          <div><div className="muted" style={{ fontSize: 12 }}>Утверждено</div><div className="table__strong">{budget.approvedTotal} ₽</div></div>
        </div>
        <div className="table-wrap" style={{ marginTop: 14 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Код</th>
                <th>Статья</th>
                <th style={{ textAlign: "right" }}>План, ₽</th>
                <th style={{ textAlign: "right" }}>Утверждено, ₽</th>
                <th>Источник</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {budgetLines.map((l) => (
                <tr key={l.code + l.description} style={l.manual ? { background: "var(--amber-50)" } : undefined}>
                  <td className="table__muted">{l.code}</td>
                  <td className="table__strong">
                    {l.description}
                    {l.manual && <Badge tone="amber">ручная</Badge>}
                  </td>
                  <td style={{ textAlign: "right" }}>{l.planned}</td>
                  <td style={{ textAlign: "right" }} className="table__strong">{l.approved}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{l.source}</td>
                  <td><Badge tone={l.statusTone}>{l.status}</Badge></td>
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
          Базовые статьи (<strong>budget_lines</strong>) формируются из итогов утверждённой сметы
          (<strong>estimates</strong>) — материалы, труд, машины, накладные, прибыль — без
          дублирования позиций. Ручная статья допускается только для расхода вне сметы, требует
          указания источника и проходит согласование (R3, крупная — R4 + MFA). Утверждение
          бюджета фиксируется в аудите.
        </div>
      </div>
    </>
  );
}
