/* Модуль «Персонал объектов». Экран 2 — карточка конкретного объекта. */
import Link from "next/link";
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { siteCard, siteWorkers } from "../../../../lib/personnel";

export default function SitePersonnelCardPage() {
  return (
    <>
      <PageHead
        title={`Персонал объекта: ${siteCard.site}`}
        desc={`Прораб: ${siteCard.foreman} · Ответственные: ${siteCard.responsible}`}
        action={
          <>
            <Link href="/personnel" className="btn btn--ghost btn--sm">К сводке</Link>
            <Link href="/personnel/daily-report" className="btn btn--primary btn--sm">Отчёт прораба</Link>
          </>
        }
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">На объекте / план</div><div className="kpi__value">{siteCard.onSite} / {siteCard.planned}</div><div className="kpi__icon kpi__icon--navy"><Icons.employees width={22} height={22} /></div></div>
        <div className="kpi"><div className="kpi__label">Бригад</div><div className="kpi__value">{siteCard.brigades}</div><div className="kpi__icon kpi__icon--emerald"><Icons.sites width={22} height={22} /></div></div>
        <div className="kpi"><div className="kpi__label">Не допущено</div><div className="kpi__value" style={{ color: "var(--red-600)" }}>1</div><div className="kpi__icon kpi__icon--red"><Icons.alert width={22} height={22} /></div></div>
        <div className="kpi"><div className="kpi__label">Фотоотчётов за смену</div><div className="kpi__value">14</div><div className="kpi__icon kpi__icon--navy"><Icons.documents width={22} height={22} /></div></div>
      </div>

      <Card title="Работники и бригады на смене" more="Фотоотчёт смены" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Работник</th>
                <th>Бригада</th>
                <th>Профессия / работа</th>
                <th>Приход / уход</th>
                <th>Смена · часы</th>
                <th>Объём</th>
                <th>Допуск</th>
                <th>Документы</th>
              </tr>
            </thead>
            <tbody>
              {siteWorkers.map((w) => (
                <tr key={w.name}>
                  <td>
                    <div className="row" style={{ gap: 10 }}>
                      <span className="avatar-sm">{w.initials}</span>
                      <Link href="/personnel/worker" className="table__strong" style={{ color: "var(--navy-600)" }}>{w.name}</Link>
                    </div>
                  </td>
                  <td>{w.brigade}</td>
                  <td>
                    <div className="table__strong">{w.profession}</div>
                    <div className="table__muted">{w.work}</div>
                  </td>
                  <td>{w.arrival} — {w.departure}</td>
                  <td>{w.shift} · {w.hours} ч</td>
                  <td>{w.volume}</td>
                  <td><Badge tone={w.clearanceTone}>{w.clearance}</Badge></td>
                  <td><Badge tone={w.docsTone}>{w.docs}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="grid grid--3">
        <Card title="Фотоотчёт смены (демо)" className="span-2">
          <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
            {["Траншея уч. 3", "Монтаж трубы", "Сварной стык", "Основание", "Обратная засыпка", "Ограждение"].map((c) => (
              <div key={c} style={{ width: 150, height: 96, borderRadius: 10, background: "linear-gradient(135deg,var(--navy-100),var(--graphite-200))", display: "flex", alignItems: "flex-end", padding: 8, border: "1px solid var(--border)" }}>
                <span style={{ fontSize: 11, color: "var(--graphite-700)", background: "rgba(255,255,255,.8)", borderRadius: 5, padding: "2px 6px" }}>{c}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Статус объекта по ОТ">
          <div className="toggle"><span className="muted">Инструктажи подписаны</span><Badge tone="amber">4 из 5</Badge></div>
          <div className="toggle"><span className="muted">Медосмотры действуют</span><Badge tone="amber">4 из 5</Badge></div>
          <div className="toggle"><span className="muted">Специальные допуски</span><Badge tone="red">1 просрочен</Badge></div>
          <div className="toggle"><span className="muted">Журналы объекта</span><Badge tone="amber">2 требуют</Badge></div>
        </Card>
      </div>
    </>
  );
}
