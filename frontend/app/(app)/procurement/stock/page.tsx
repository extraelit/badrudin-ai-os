"use client";

/* «Складской учёт и остатки» — рабочий контур (backend /warehouse). Остатки,
 * свободный остаток, резервы, точка дозаказа, журнал движений (проводок).
 * Данные из backend, без mock; без backend — честное пустое состояние. */
import { useEffect, useState } from "react";
import { PageHead, Kpi, Card, Badge } from "../../../../components/ui";
import { apiBaseConfigured } from "../../../../lib/authApi";
import {
  inventoryApi,
  type StockSummary,
  type StockRow,
  type LedgerRow,
  type Reservation,
  type WarehouseRef,
} from "../../../../lib/inventoryApi";

const TX: Record<string, "gray" | "amber" | "navy" | "emerald" | "red"> = {
  receipt: "emerald", return: "emerald", transfer_in: "navy", issue: "amber",
  transfer_out: "amber", write_off: "red", adjustment: "gray",
};

export default function StockPage() {
  const live = apiBaseConfigured();
  const [warehouses, setWarehouses] = useState<WarehouseRef[]>([]);
  const [wid, setWid] = useState("");
  const [sum, setSum] = useState<StockSummary | null>(null);
  const [stock, setStock] = useState<StockRow[]>([]);
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => {
    if (!live) return;
    inventoryApi.summary().then(setSum).catch(() => undefined);
    inventoryApi.stock(wid || undefined).then(setStock).catch(() => undefined);
    inventoryApi.ledger(wid || undefined).then(setLedger).catch(() => undefined);
    inventoryApi.reservations(wid || undefined, "active").then(setReservations).catch(() => undefined);
  };
  useEffect(() => {
    if (!live) return;
    inventoryApi.listWarehouses().then(setWarehouses).catch(() => undefined);
  }, [live]);
  useEffect(reload, [live, wid]);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setErr(null);
    try { await fn(); setMsg(ok); reload(); } catch (e) { setErr((e as Error).message); }
  }

  if (!live) {
    return (
      <>
        <PageHead title="Складской учёт и остатки" desc="Остатки, резервы, движения, точка дозаказа" />
        <div className="alert"><div className="alert__icon">ℹ</div><div className="muted" style={{ fontSize: 13 }}>Backend не подключён. Рабочий контур загружает данные из backend после входа.</div></div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Складской учёт и остатки"
        desc="Остатки и свободный остаток, резервы, движения · данные из backend"
        action={
          <select value={wid} onChange={(e) => setWid(e.target.value)} style={sel}>
            <option value="">— все склады —</option>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        }
      />
      {msg && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">✓</div><div style={{ fontSize: 13 }}>{msg}</div></div>}
      {err && <div className="alert" style={{ marginBottom: 12 }}><div className="alert__icon">⚠</div><div style={{ fontSize: 13 }}>{err}</div></div>}

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        <Kpi label="Позиций на складах" value={String(sum?.positions ?? "—")} icon="sites" tone="navy" foot={`складов: ${sum?.warehouses_with_stock ?? 0}`} />
        <Kpi label="Стоимость запаса" value={`${sum?.total_value ?? "—"} ₽`} icon="finance" tone="navy" foot="по средней себестоимости" />
        <Kpi label="Позиций в резерве" value={String(sum?.reserved_positions ?? "—")} icon="approvals" tone="amber" foot="активные резервы" />
        <Kpi label="Ниже точки дозаказа" value={String(sum?.low_stock ?? "—")} icon="reports" tone={sum && sum.low_stock > 0 ? "amber" : "emerald"} foot={`отрицательный остаток: ${sum?.negative_stock ?? 0}`} />
      </div>

      <Card title="Остатки" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Материал</th><th style={{ textAlign: "right" }}>Остаток</th><th style={{ textAlign: "right" }}>Резерв</th><th style={{ textAlign: "right" }}>Свободно</th><th style={{ textAlign: "right" }}>Мин.</th><th style={{ textAlign: "right" }}>Ср. цена</th><th>Резерв</th></tr></thead>
            <tbody>
              {stock.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 16 }}>Остатков нет.</td></tr>}
              {stock.map((b) => (
                <tr key={`${b.warehouse_id}-${b.material_id}-${b.location_id ?? ""}`}>
                  <td className="table__strong">{b.material_name || b.material_id.slice(0, 8)}{b.low && <> <Badge tone="amber">низкий</Badge></>}</td>
                  <td style={{ textAlign: "right" }}>{b.quantity}</td>
                  <td style={{ textAlign: "right" }}>{b.reserved_quantity}</td>
                  <td style={{ textAlign: "right" }}>{b.available_quantity}</td>
                  <td style={{ textAlign: "right" }} className="table__muted">{b.minimum_quantity}</td>
                  <td style={{ textAlign: "right" }}>{b.average_unit_cost}</td>
                  <td>
                    {Number(b.available_quantity) > 0 && wid && (
                      <button className="btn btn--ghost btn--sm" onClick={() => {
                        const q = Number(prompt("Количество к резерву:", "1"));
                        if (q > 0) run(() => inventoryApi.reserve({ warehouse_id: b.warehouse_id, material_id: b.material_id, quantity: q }), "Резерв создан");
                      }}>Зарезервировать</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Активные резервы" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Материал</th><th style={{ textAlign: "right" }}>Кол-во</th><th>Основание</th><th>Причина</th><th>Действие</th></tr></thead>
            <tbody>
              {reservations.length === 0 && <tr><td colSpan={5} className="muted" style={{ padding: 16 }}>Активных резервов нет.</td></tr>}
              {reservations.map((r) => (
                <tr key={r.id}>
                  <td className="table__strong">{r.material_name || r.material_id.slice(0, 8)}</td>
                  <td style={{ textAlign: "right" }}>{r.quantity}</td>
                  <td>{r.purchase_order_id ? <Badge tone="navy">заказ</Badge> : r.material_request_id ? <Badge tone="navy">заявка</Badge> : <Badge tone="gray">ручной</Badge>}</td>
                  <td className="table__muted">{r.reason || "—"}</td>
                  <td><button className="btn btn--ghost btn--sm" onClick={() => run(() => inventoryApi.release(r.id), "Резерв снят")}>Снять</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <Card title="Журнал движений (проводки)" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Материал</th><th>Тип</th><th style={{ textAlign: "right" }}>Кол-во</th><th>Основание</th></tr></thead>
            <tbody>
              {ledger.length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Движений нет.</td></tr>}
              {ledger.map((t) => (
                <tr key={t.id}>
                  <td className="table__strong">{t.material_name || t.material_id.slice(0, 8)}</td>
                  <td><Badge tone={TX[t.transaction_type] || "gray"}>{t.transaction_type}</Badge></td>
                  <td style={{ textAlign: "right" }}>{t.quantity}</td>
                  <td className="table__muted">{t.source_type || "—"}</td>
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
          Свободный остаток = остаток − резерв. Ручной резерв уменьшает свободный остаток и не
          позволяет зарезервировать больше доступного. Проводки склада идемпотентны (защита от
          двойного проведения). Точка дозаказа даёт сигнал «низкий остаток». Чтение —
          <strong> warehouse.view</strong>, изменение — <strong>warehouse.manage</strong>; доступ к
          складу ограничен доступными проектами. Все действия — в журнале аудита.
        </div>
      </div>
    </>
  );
}

const sel: React.CSSProperties = { padding: "8px 12px", borderRadius: 8, border: "1px solid var(--line,#e2e8f0)", fontSize: 13 };
