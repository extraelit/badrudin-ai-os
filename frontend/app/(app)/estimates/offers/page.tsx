/* Модуль «Сметы и ценообразование». Экран 5 — коммерческие предложения. */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { offers } from "../../../../lib/estimates";

export default function OffersPage() {
  return (
    <>
      <PageHead
        title="Коммерческие предложения"
        desc="Наценка к смете, итоговая цена заказчику, уровень согласования R3/R4"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новое КП</button>}
      />

      <Card title="Коммерческие предложения" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>№</th>
                <th>Основание (смета)</th>
                <th>База (с НДС)</th>
                <th>Наценка</th>
                <th>Итоговая цена</th>
                <th>Риск</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {offers.map((o) => (
                <tr key={o.id}>
                  <td className="table__muted">{o.id}</td>
                  <td className="table__strong">{o.estimate}</td>
                  <td>{o.base}</td>
                  <td>{o.markup}</td>
                  <td className="table__strong" style={{ color: "var(--emerald-700)" }}>{o.offer}</td>
                  <td><Risk level={o.risk} /></td>
                  <td><Badge tone={o.statusTone}>{o.status}</Badge></td>
                  <td>
                    {o.status === "На согласовании" ? (
                      <div className="row" style={{ gap: 6 }}>
                        <button className="btn btn--emerald btn--sm">Согласовать</button>
                        <button className="btn btn--ghost btn--sm">Отклонить</button>
                      </div>
                    ) : (
                      <span className="muted" style={{ fontSize: 12 }}>{o.status === "Черновик" ? "На согласование" : "Завершено"}</span>
                    )}
                  </td>
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
          <div className="table__strong">Утверждение итоговой цены — только человеком</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            КП уровня <strong>R3</strong> подтверждает уполномоченное лицо; уровня <strong>R4</strong>
            {" "}(крупная или массовая сумма) — с усиленной аутентификацией (MFA). Порог суммы настраивается
            для организации. ИИ готовит расчёт и наценку, но не отправляет цену заказчику самостоятельно.
          </div>
        </div>
      </div>
    </>
  );
}
