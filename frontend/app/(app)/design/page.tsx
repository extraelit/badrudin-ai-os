"use client";

/* Модуль «Проектирование и дизайн». Экран 1 — рабочее пространство проекта (ГИП).
 * По умолчанию mock-данные; при доступном backend подмешивается живая сводка. */
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHead, Kpi, Card, Badge, Progress } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { designProject, designKpis, disciplines, brief, designIssues } from "../../../lib/design";
import { designApi } from "../../../lib/designApi";

export default function DesignOverviewPage() {
  const [kpis, setKpis] = useState(designKpis);
  const [live, setLive] = useState(false);

  useEffect(() => {
    designApi
      .getOverview("demo")
      .then((o) => {
        setKpis((prev) =>
          prev.map((k) => {
            if (k.label === "Разделы проекта")
              return { ...k, value: String(o.disciplines_total), trend: `${o.disciplines_issued} выпущены` };
            if (k.label === "Средняя готовность") return { ...k, value: `${o.avg_completion}%` };
            if (k.label === "Открытые замечания")
              return { ...k, value: String(o.issues_open), trend: `${o.issues_critical} критич.` };
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
        title="Проектирование и дизайн — рабочее пространство"
        desc={`${designProject.name} · ГИП: ${designProject.gip}` + (live ? " · данные из backend" : "")}
        action={<Link href="/design/disciplines" className="btn btn--primary btn--sm">Статус разделов</Link>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {kpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <div className="grid grid--2" style={{ marginBottom: 18 }}>
        <Card title="Готовность разделов" more="ГИП" flush>
          <div className="list">
            {disciplines.slice(0, 5).map((d) => (
              <div key={d.code} className="list__item">
                <span className="badge badge--navy" style={{ minWidth: 44, justifyContent: "center" }}>{d.code}</span>
                <div className="list__main">
                  <div className="list__title" style={{ fontSize: 13 }}>{d.name}</div>
                  <div style={{ marginTop: 6 }}><Progress value={d.completion} tone={d.completion < 50 ? "amber" : undefined} /></div>
                </div>
                <Badge tone={d.gipTone}>{d.gip}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <div className="stack">
          <Card title="Техническое задание" more="Открыть">
            <div className="row row--between">
              <div>
                <div className="list__title">{brief.title}</div>
                <div className="list__sub">Заказчик: {brief.client} · срок {brief.target}</div>
              </div>
              <Badge tone={brief.statusTone}>{brief.status}</Badge>
            </div>
          </Card>
          <Card title="Последние замечания" more="Все замечания" flush>
            <div className="list">
              {designIssues.slice(0, 3).map((i) => (
                <div key={i.id} className="list__item">
                  <div className="list__icon" style={{ background: "var(--amber-100)", color: "var(--amber-600)" }}>
                    <Icons.alert width={18} height={18} />
                  </div>
                  <div className="list__main">
                    <div className="list__title" style={{ fontSize: 13 }}>{i.title}</div>
                    <div className="list__sub">{i.source} · {i.responsible} · задача {i.task}</div>
                  </div>
                  <Badge tone={i.severityTone}>{i.severity}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Выпуск рабочей документации в производство — только через утверждённую версию документа
          и согласование <strong>R3</strong>; аннулирование утверждённой документации — <strong>R4</strong>
          {" "}с усиленной аутентификацией. Замечания автоматически становятся задачами с ответственным и сроком.
        </div>
      </div>
    </>
  );
}
