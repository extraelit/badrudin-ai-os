"use client";

/* Модуль «Персонал объектов». Экран 1 — сводка директора по всем объектам.
 *
 * По умолчанию отображаются демонстрационные (mock) данные. Если задан
 * NEXT_PUBLIC_API_BASE_URL и backend доступен, живые показатели по объектам
 * подмешиваются поверх mock без изменения дизайна (graceful fallback). */
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHead, Card, Badge, Kpi } from "../../../components/ui";
import {
  directorSummary,
  sitePersonnel,
  personnelWidgets,
  type SitePersonnelRow,
} from "../../../lib/personnel";
import { personnelApi } from "../../../lib/personnelApi";

export default function PersonnelSummaryPage() {
  const s = directorSummary;
  const [rows, setRows] = useState<SitePersonnelRow[]>(sitePersonnel);
  const [live, setLive] = useState(false);

  useEffect(() => {
    // Живые данные подмешиваются только при доступном backend (иначе — mock).
    personnelApi
      .getDirectorSummary()
      .then((summary) => {
        const byName = new Map(summary.sites.map((x) => [x.site_name, x]));
        setRows((prev) =>
          prev.map((r) => {
            const api = byName.get(r.site);
            if (!api) return r;
            return {
              ...r,
              actual: api.workers,
              onSite: api.on_site,
              hoursDay: api.hours_day,
              overtime: api.overtime,
              idle: api.idle,
              noPermit: api.without_clearance,
              unfilledJournals: api.unfilled_journals,
            };
          })
        );
        setLive(true);
      })
      .catch(() => setLive(false));
  }, []);

  return (
    <>
      <PageHead
        title="Персонал объектов — сводка директора"
        desc={
          "Производственный учёт по всем строительным объектам · 19 июля 2026" +
          (live ? " · данные из backend" : "")
        }
      />

      <div className="grid grid--3" style={{ marginBottom: 18 }}>
        {personnelWidgets.map((w) => (
          <Kpi key={w.label} {...w} />
        ))}
      </div>

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Плановая / фактическая</div><div className="kpi__value">{s.planned} / {s.actual}</div><div className="kpi__foot"><span className="muted">численность</span></div></div>
        <div className="kpi"><div className="kpi__label">На объекте сейчас / отсутствуют</div><div className="kpi__value">{s.onSite} / {s.absent}</div><div className="kpi__foot"><span className="muted">чел.</span></div></div>
        <div className="kpi"><div className="kpi__label">Часы за день / месяц</div><div className="kpi__value" style={{ fontSize: 22 }}>{s.hoursDay} / {s.hoursMonth.toLocaleString("ru-RU")}</div><div className="kpi__foot"><span className="muted">ч</span></div></div>
        <div className="kpi"><div className="kpi__label">Переработки / простои</div><div className="kpi__value">{s.overtime} / {s.idle}</div><div className="kpi__foot"><span className="muted">ч за день</span></div></div>
      </div>

      <Card title="Показатели по объектам" more="Табель" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Объект</th>
                <th>План / факт</th>
                <th>На объекте</th>
                <th>Отсутств.</th>
                <th>Часы (день)</th>
                <th>Переработ.</th>
                <th>Простой</th>
                <th>ФОТ, млн ₽</th>
                <th>Без допуска</th>
                <th>Инстр. не подп.</th>
                <th>Журналы</th>
                <th>Наруш.</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.site}>
                  <td>
                    <Link href="/personnel/site" className="table__strong" style={{ color: "var(--navy-600)" }}>
                      {r.site}
                    </Link>
                  </td>
                  <td>{r.planned} / {r.actual}</td>
                  <td className="table__strong">{r.onSite}</td>
                  <td>{r.absent}</td>
                  <td>{r.hoursDay}</td>
                  <td>{r.overtime}</td>
                  <td style={r.idle > 0 ? { color: "var(--amber-600)", fontWeight: 600 } : undefined}>{r.idle}</td>
                  <td className="table__strong">{r.fotMonthM.toFixed(2)}</td>
                  <td>{r.noPermit > 0 ? <Badge tone="red">{r.noPermit}</Badge> : <span className="muted">0</span>}</td>
                  <td>{r.unsignedBriefings > 0 ? <Badge tone="amber">{r.unsignedBriefings}</Badge> : <span className="muted">0</span>}</td>
                  <td>{r.unfilledJournals > 0 ? <Badge tone="amber">{r.unfilledJournals}</Badge> : <span className="muted">0</span>}</td>
                  <td>{r.violations > 0 ? <Badge tone="red">{r.violations}</Badge> : <span className="muted">0</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="alert alert--danger">
        <div className="alert__icon">⚠</div>
        <div>
          <div className="table__strong">Критические нарушения: {s.violations}</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            {s.noPermit} работников без действующего допуска, {s.unsignedBriefings} неподписанных инструктажей,
            {" "}{s.unfilledJournals} незаполненных журналов. Работник не может быть отмечен допущенным без
            обязательных документов (охрана труда).
          </div>
        </div>
      </div>
    </>
  );
}
