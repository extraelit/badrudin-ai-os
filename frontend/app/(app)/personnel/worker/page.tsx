/* Модуль «Персонал объектов». Экран 7 — карточка работника на объекте. */
import Link from "next/link";
import { PageHead, Card, Badge } from "../../../../components/ui";
import {
  worker,
  workerSites,
  workerBriefings,
  workerPermits,
  workerViolations,
  workerPayroll,
} from "../../../../lib/personnel";

export default function WorkerCardPage() {
  return (
    <>
      <PageHead
        title="Карточка работника на объекте"
        action={<Link href="/personnel/site" className="btn btn--ghost btn--sm">К объекту</Link>}
      />

      <Card style={{ marginBottom: 18 }}>
        <div className="row" style={{ gap: 16 }}>
          <span className="avatar__img" style={{ width: 60, height: 60, fontSize: 20 }}>{worker.initials}</span>
          <div style={{ flex: 1 }}>
            <div className="page-head__title" style={{ fontSize: 20 }}>{worker.name}</div>
            <div className="muted">{worker.profession} · {worker.brigade}</div>
          </div>
          <div className="row" style={{ gap: 20 }}>
            <div><div className="kpi__label">Статус</div><Badge tone={worker.statusTone}>{worker.status}</Badge></div>
            <div><div className="kpi__label">Принят</div><div className="table__strong">{worker.hiredAt}</div></div>
            <div><div className="kpi__label">Телефон</div><div className="table__muted">{worker.phone}</div></div>
          </div>
        </div>
      </Card>

      <div className="grid grid--2" style={{ marginBottom: 18 }}>
        <Card title="Связанные объекты и переводы" flush>
          <div className="list">
            {workerSites.map((s) => (
              <div key={s.site} className="list__item">
                <div className="list__main">
                  <div className="list__title">{s.site}</div>
                  <div className="list__sub">{s.role} · {s.period}</div>
                </div>
                {s.current ? <Badge tone="emerald">Текущий</Badge> : <Badge tone="gray">Завершён</Badge>}
              </div>
            ))}
          </div>
        </Card>

        <Card title="Начисления по месяцам" flush>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Месяц</th><th>Начислено</th><th>Выплачено</th><th>Статус</th></tr></thead>
              <tbody>
                {workerPayroll.map((p) => (
                  <tr key={p.month}>
                    <td className="table__strong">{p.month}</td>
                    <td>{p.accrued}</td>
                    <td>{p.paid}</td>
                    <td><Badge tone={p.tone}>{p.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="grid grid--3">
        <Card title="Инструктажи" flush>
          <div className="list">
            {workerBriefings.map((b) => (
              <div key={b.name} className="list__item">
                <div className="list__main">
                  <div className="list__title" style={{ fontSize: 13 }}>{b.name}</div>
                  <div className="list__sub">{b.date}</div>
                </div>
                <Badge tone={b.signed ? "emerald" : "red"}>{b.signed ? "Подписан" : "Нет"}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Допуски и удостоверения" flush>
          <div className="list">
            {workerPermits.map((p) => (
              <div key={p.name} className="list__item">
                <div className="list__main">
                  <div className="list__title" style={{ fontSize: 13 }}>{p.name}</div>
                  <div className="list__sub">действует до {p.until}</div>
                </div>
                <Badge tone={p.tone}>{p.tone === "amber" ? "Скоро" : "ОК"}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Нарушения" flush>
          {workerViolations.length === 0 ? (
            <div className="card__body muted">Нарушений нет.</div>
          ) : (
            <div className="list">
              {workerViolations.map((v, i) => (
                <div key={i} className="list__item">
                  <div className="list__main">
                    <div className="list__title" style={{ fontSize: 13 }}>{v.text}</div>
                    <div className="list__sub">{v.date}</div>
                  </div>
                  <Badge tone={v.tone}>{v.severity}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
