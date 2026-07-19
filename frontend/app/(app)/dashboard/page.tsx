/* Экран 1. Главная панель генерального директора. */
import Link from "next/link";
import { PageHead, Kpi, Card, Badge, Risk, Bars } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import {
  ceoKpis,
  revenueByMonth,
  ceoPriorities,
  ceoRisks,
  dailyDigest,
  sites,
} from "../../../lib/mock";
import { personnelWidgets } from "../../../lib/personnel";

export default function DashboardPage() {
  return (
    <>
      <PageHead
        title="Панель генерального директора"
        desc="Утренняя сводка, приоритеты и критические риски на 19 июля 2026"
        action={
          <>
            <button className="btn btn--ghost btn--sm">Экспорт сводки</button>
            <button className="btn btn--primary btn--sm">
              <Icons.plus width={16} height={16} /> Новое поручение
            </button>
          </>
        }
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {ceoKpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <div className="row row--between" style={{ margin: "6px 2px 12px" }}>
        <h2 style={{ fontSize: 16 }}>Персонал на объектах сегодня</h2>
        <Link href="/personnel" className="link-more">Открыть модуль →</Link>
      </div>
      <div className="grid grid--3" style={{ marginBottom: 22 }}>
        {personnelWidgets.map((w) => (
          <Kpi key={w.label} {...w} />
        ))}
      </div>

      <div className="grid grid--3" style={{ marginBottom: 18 }}>
        <Card title="Динамика выполненных работ, млн ₽" more="Финансы" className="span-2">
          <Bars data={revenueByMonth} />
        </Card>
        <Card title="Критические риски" more="Все риски">
          <div className="stack" style={{ gap: 12 }}>
            {ceoRisks.map((r) => (
              <div key={r.title} className="row" style={{ alignItems: "flex-start", gap: 10 }}>
                <span className={`kpi__icon kpi__icon--${r.tone}`} style={{ position: "static", width: 34, height: 34 }}>
                  <Icons.alert width={17} height={17} />
                </span>
                <div>
                  <div className="list__title" style={{ fontSize: 13 }}>{r.title}</div>
                  <div className="muted" style={{ fontSize: 12 }}>Уровень: {r.level}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid--2">
        <Card title="Требуют вашего решения" more="Согласования" flush>
          <div className="list">
            {ceoPriorities.map((p) => (
              <div key={p.title} className="list__item">
                <div className="list__main">
                  <div className="list__title">{p.title}</div>
                  <div className="list__sub">{p.meta}</div>
                </div>
                <Risk level={p.risk} />
              </div>
            ))}
          </div>
        </Card>

        <div className="stack">
          <Card title="Лента событий дня" flush>
            <div className="list">
              {dailyDigest.map((d) => (
                <div key={d.time} className="list__item">
                  <span className="badge badge--navy" style={{ minWidth: 52, justifyContent: "center" }}>
                    {d.time}
                  </span>
                  <div className="list__sub" style={{ color: "var(--graphite-700)" }}>{d.text}</div>
                </div>
              ))}
            </div>
          </Card>
          <Card title="Состояние ключевых объектов" flush>
            <div className="list">
              {sites.slice(0, 3).map((s) => (
                <div key={s.id} className="list__item">
                  <div className="list__icon"><Icons.sites width={19} height={19} /></div>
                  <div className="list__main">
                    <div className="list__title">{s.name}</div>
                    <div className="list__sub">Готовность {s.progress}% · срок {s.deadline}</div>
                  </div>
                  <Badge tone={s.statusTone}>{s.status}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
