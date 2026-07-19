"use client";

/* Модуль «Сметы и ценообразование». Экран 1 — сводка сметного отдела.
 * По умолчанию mock; при доступном backend подмешивается живая сводка. */
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHead, Kpi, Card, Badge, Risk } from "../../../components/ui";
import { estimateProject, estimateKpis, estimates, offers } from "../../../lib/estimates";
import { estimatesApi } from "../../../lib/estimatesApi";

export default function EstimatesOverviewPage() {
  const [kpis, setKpis] = useState(estimateKpis);
  const [live, setLive] = useState(false);

  useEffect(() => {
    estimatesApi
      .getSummary("demo")
      .then((s) => {
        setKpis((prev) =>
          prev.map((k) => {
            if (k.label === "Сметы по проекту")
              return { ...k, value: String(s.estimates_total), trend: `${s.approved_total} утверждены` };
            if (k.label === "КП на согласовании") return { ...k, value: String(s.offers_pending) };
            return k;
          })
        );
        setLive(true);
      })
      .catch(() => setLive(false));
  }, []);

  return (
    <>
      <PageHead
        title="Сметы и ценообразование — сводка"
        desc={`${estimateProject.name} · ${estimateProject.role}` + (live ? " · данные из backend" : "")}
        action={<Link href="/estimates/editor" className="btn btn--primary btn--sm">Открыть смету</Link>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {kpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <Card title="Сметы по проекту" more="План-факт" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Наименование</th>
                <th>Тип</th>
                <th>Версия</th>
                <th>Стоимость (с НДС)</th>
                <th>Отклонение</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {estimates.map((e) => (
                <tr key={e.id}>
                  <td className="table__muted">{e.id}</td>
                  <td>
                    <Link href="/estimates/editor" className="table__strong" style={{ color: "var(--navy-600)" }}>{e.name}</Link>
                  </td>
                  <td><span className="badge badge--navy">{e.type}</span></td>
                  <td>v{e.version}</td>
                  <td className="table__strong">{e.grand}</td>
                  <td><Badge tone={e.deviationTone}>{e.deviation}</Badge></td>
                  <td><Badge tone={e.statusTone}>{e.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="grid grid--2">
        <Card title="Требуют решения директора" flush>
          <div className="list">
            {offers.filter((o) => o.status === "На согласовании").map((o) => (
              <div key={o.id} className="list__item">
                <div className="list__main">
                  <div className="list__title">КП {o.id} · {o.estimate}</div>
                  <div className="list__sub">Итоговая цена {o.offer} · наценка {o.markup}</div>
                </div>
                <Risk level={o.risk} />
              </div>
            ))}
          </div>
        </Card>
        <div className="alert" style={{ alignItems: "flex-start" }}>
          <div className="alert__icon">ℹ</div>
          <div className="muted" style={{ fontSize: 13 }}>
            Итоговая цена заказчику формируется как КП с наценкой и утверждается человеком:
            <strong> R3</strong> — обычная сумма, <strong> R4 + MFA</strong> — крупная/массовая
            (порог настраивается для организации). Утверждённую смету нельзя менять напрямую —
            только новой версией или через change order. Все действия — в журнале аудита.
          </div>
        </div>
      </div>
    </>
  );
}
