"use client";

/* Модуль «Ядро CRM». Экран 1 — сводка и аналитика продаж.
 * По умолчанию mock; при доступном backend подмешивается живая аналитика. */
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHead, Kpi, Card, Badge, Progress } from "../../../components/ui";
import { crmKpis, funnel, managers, lossReasons } from "../../../lib/crm";
import { crmApi } from "../../../lib/crmApi";

export default function CrmOverviewPage() {
  const [kpis, setKpis] = useState(crmKpis);
  const [live, setLive] = useState(false);

  useEffect(() => {
    crmApi
      .getAnalytics(2026)
      .then((a) => {
        setKpis((prev) =>
          prev.map((k) => {
            if (k.label === "Сделки в работе") return { ...k, value: String(a.open_count) };
            if (k.label === "Конверсия") return { ...k, value: `${a.conversion_percent} %` };
            return k;
          })
        );
        setLive(true);
      })
      .catch(() => setLive(false));
  }, []);

  const maxCount = Math.max(...funnel.map((s) => s.count));

  return (
    <>
      <PageHead
        title="CRM — сводка и аналитика продаж"
        desc={"Отдел продаж: воронка, конверсия, план-факт" + (live ? " · данные из backend" : "")}
        action={<Link href="/crm/deals" className="btn btn--primary btn--sm">Открыть воронку</Link>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {kpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <Card title="Воронка продаж" more="Настраиваемые этапы" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Этап</th>
                <th>Сделок</th>
                <th style={{ width: "40%" }}>Заполненность</th>
                <th>Сумма</th>
                <th>Вероятность</th>
              </tr>
            </thead>
            <tbody>
              {funnel.map((s) => (
                <tr key={s.name}>
                  <td className="table__strong">
                    {s.name}
                    {s.won && <Badge tone="emerald">выигрыш</Badge>}
                    {s.lost && <Badge tone="red">потеря</Badge>}
                  </td>
                  <td>{s.count}</td>
                  <td>
                    <div className="progress">
                      <div
                        className={`progress__bar${s.lost ? " progress__bar--red" : s.won ? " progress__bar--emerald" : ""}`}
                        style={{ width: `${Math.max((s.count / maxCount) * 100, 4)}%` }}
                      />
                    </div>
                  </td>
                  <td className="table__strong">{s.amount}</td>
                  <td>{s.probability}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="grid grid--2">
        <Card title="План-факт по менеджерам" flush>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Менеджер</th><th>Выиграно</th><th>Цель</th><th style={{ width: "35%" }}>План-факт</th></tr>
              </thead>
              <tbody>
                {managers.map((m) => (
                  <tr key={m.name}>
                    <td className="table__strong">{m.name}</td>
                    <td>{m.wonAmount}</td>
                    <td>{m.target}</td>
                    <td><Progress value={m.planFact} tone={m.planFact >= 85 ? "emerald" : m.planFact >= 60 ? "amber" : "red"} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Причины проигрыша" flush>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Причина</th><th>Сделок</th><th>Сумма</th></tr>
              </thead>
              <tbody>
                {lossReasons.map((l) => (
                  <tr key={l.reason}>
                    <td className="table__strong">{l.reason}</td>
                    <td>{l.count}</td>
                    <td>{l.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Аналитика строится по единой воронке (<strong>pipeline_stages</strong>) и сделкам
          (<strong>deals</strong>) без дублирования. Коммерческие предложения переиспользуют
          <strong> commercial_offers</strong>. Цепочка: лид → сделка → КП → договор → проект;
          проект создаётся только после выигранной сделки и утверждённого/подписанного договора.
        </div>
      </div>
    </>
  );
}
