"use client";

/* Модуль «Снабжение и закупки». Экран 1 — сводка снабжения.
 * По умолчанию mock; при доступном backend подмешивается живая сводка. */
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHead, Kpi, Card, Badge, Risk } from "../../../components/ui";
import { procKpis, orders } from "../../../lib/procurement";
import { procurementApi } from "../../../lib/procurementApi";

export default function ProcurementSummaryPage() {
  const [kpis, setKpis] = useState(procKpis);
  const [live, setLive] = useState(false);

  useEffect(() => {
    procurementApi
      .getSummary()
      .then((s) => {
        setKpis((prev) =>
          prev.map((k) => {
            if (k.label === "Открытые заявки") return { ...k, value: String(s.requests_open) };
            if (k.label === "Заказы в работе") return { ...k, value: String(s.orders_active) };
            if (k.label === "Ждут согласования") return { ...k, value: String(s.orders_pending + s.writeoffs_pending) };
            if (k.label === "Позиции на складе") return { ...k, value: String(s.stock_positions), trend: `${s.warehouses} склада` };
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
        title="Снабжение и закупки — сводка"
        desc={"Заявки, запросы цен, заказы, поставки, склад и согласования" + (live ? " · данные из backend" : "")}
        action={<Link href="/procurement/requests" className="btn btn--primary btn--sm">Заявки</Link>}
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {kpis.map((k) => (
          <Kpi key={k.label} {...k} />
        ))}
      </div>

      <div className="grid grid--2" style={{ marginBottom: 18 }}>
        <Card title="Требуют решения (заказы/списания)" more="Заказы" flush>
          <div className="list">
            {orders.filter((o) => o.status === "На согласовании").map((o) => (
              <div key={o.id} className="list__item">
                <div className="list__main">
                  <div className="list__title">Заказ {o.id} · {o.supplier}</div>
                  <div className="list__sub">{o.material} · {o.amount}</div>
                </div>
                <Risk level={o.risk} />
              </div>
            ))}
          </div>
        </Card>

        <div className="alert" style={{ alignItems: "flex-start" }}>
          <div className="alert__icon">ℹ</div>
          <div className="muted" style={{ fontSize: 13 }}>
            Полный цикл: заявка → запрос цен и сравнение КП → заказ → поступление и входной контроль →
            оприходование на склад → выдача на объект, с перемещением, возвратом, списанием и инвентаризацией.
            Согласование заказа/списания — <strong>R3</strong> (крупное — <strong>R4 + MFA</strong>, порог настраивается для
            организации). Складские проводки идемпотентны; все действия — в журнале аудита.
          </div>
        </div>
      </div>

      <Card title="Быстрые переходы" flush>
        <div className="list">
          {[
            ["Заявки на материалы", "/procurement/requests"],
            ["Запросы цен и сравнение КП", "/procurement/rfq"],
            ["Заказы поставщикам", "/procurement/orders"],
            ["Поступление и приёмка", "/procurement/receipts"],
            ["Склад: остатки и движения", "/procurement/warehouse"],
            ["Выдача и инвентаризация", "/procurement/inventory"],
          ].map(([label, href]) => (
            <Link key={href} href={href} className="list__item" style={{ color: "inherit" }}>
              <div className="list__main"><div className="list__title" style={{ fontSize: 13 }}>{label}</div></div>
              <span className="link-more">Открыть →</span>
            </Link>
          ))}
        </div>
      </Card>
    </>
  );
}
