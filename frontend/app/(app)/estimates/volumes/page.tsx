/* Модуль «Сметы и ценообразование». Экран 3 — ведомость объёмов работ. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { workVolumes } from "../../../../lib/estimates";

export default function VolumesPage() {
  return (
    <>
      <PageHead
        title="Ведомость объёмов работ"
        desc="Плановые и фактические объёмы, прораб, подтверждение и статус проверки"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Внести объём</button>}
      />

      <Card title="Объёмы работ (связаны с позициями смет)" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Работа</th>
                <th>Ед.</th>
                <th>План</th>
                <th>Факт</th>
                <th>Выполнение</th>
                <th>Прораб</th>
                <th>Дата</th>
                <th>Проверка</th>
              </tr>
            </thead>
            <tbody>
              {workVolumes.map((v) => {
                const pct = Math.round((parseFloat(v.actual.replace(/\s/g, "")) / parseFloat(v.planned.replace(/\s/g, ""))) * 100);
                return (
                  <tr key={v.work}>
                    <td className="table__strong">{v.work}</td>
                    <td>{v.unit}</td>
                    <td>{v.planned}</td>
                    <td>{v.actual}</td>
                    <td style={{ minWidth: 130 }}>
                      <div className="progress-row">
                        <div className="progress"><div className={`progress__bar${pct < 70 ? " progress__bar--amber" : ""}`} style={{ width: `${Math.min(pct, 100)}%` }} /></div>
                        <span>{pct}%</span>
                      </div>
                    </td>
                    <td>{v.foreman}</td>
                    <td>{v.date}</td>
                    <td><Badge tone={v.vTone}>{v.verification}</Badge></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Каждый фактический объём связан с позицией сметы, проектом, объектом, зоной/участком,
          датой, единицей, прорабом и подтверждающими материалами; статус проверки — pending/verified/rejected.
          Отклонённые объёмы не учитываются в план-факте.
        </div>
      </div>
    </>
  );
}
