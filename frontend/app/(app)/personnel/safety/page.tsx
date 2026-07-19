/* Модуль «Персонал объектов». Экран 5 — охрана труда и допуски. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons, type IconName } from "../../../../lib/icons";
import { safety, safetyBriefings } from "../../../../lib/personnel";

function Check({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="badge badge--emerald" style={{ minWidth: 30, justifyContent: "center" }}>✓</span>
  ) : (
    <span className="badge badge--red" style={{ minWidth: 30, justifyContent: "center" }}>✕</span>
  );
}

export default function SafetyPage() {
  return (
    <>
      <PageHead
        title="Охрана труда и допуски"
        desc="Инструктажи, медосмотры, удостоверения и допуски к специальным работам"
      />

      <div className="grid grid--3" style={{ marginBottom: 18 }}>
        {safetyBriefings.map((b) => {
          const Icon = Icons[b.icon as IconName];
          return (
            <div key={b.name} className="card">
              <div className="card__body row" style={{ gap: 12 }}>
                <span className="list__icon"><Icon width={20} height={20} /></span>
                <div>
                  <div className="list__title">{b.name}</div>
                  <div className="list__sub">{b.desc}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <Card title="Допуск работников к работе" more="Документы" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Работник</th>
                <th>Профессия</th>
                <th>Вводный</th>
                <th>Первичный</th>
                <th>Целевой</th>
                <th>Медосмотр</th>
                <th>Удостоверения</th>
                <th>Спец. допуски</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {safety.map((r) => (
                <tr key={r.worker}>
                  <td className="table__strong">{r.worker}</td>
                  <td>{r.profession}</td>
                  <td><Check ok={r.intro} /></td>
                  <td><Check ok={r.primary} /></td>
                  <td><Check ok={r.daily} /></td>
                  <td><Badge tone={r.medicalTone}>{r.medical}</Badge></td>
                  <td className="table__muted">{r.certs}</td>
                  <td><Badge tone={r.permitTone}>{r.permits}</Badge></td>
                  <td><Badge tone={r.statusTone}>{r.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 18 }} />

      <div className="grid grid--2">
        <div className="alert alert--danger">
          <div className="alert__icon">⚠</div>
          <div>
            <div className="table__strong">Автоматические предупреждения о просрочке</div>
            <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
              Сварщик Идрисов Х. — просрочен медосмотр и допуск на сварочные работы.
              Бетонщик Юсупов Д. — медосмотр истекает в 08.2026.
            </div>
          </div>
        </div>
        <div className="alert">
          <div className="alert__icon">🔒</div>
          <div>
            <div className="table__strong">Запрет допуска без документов</div>
            <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
              Работника нельзя отметить «допущен» без действующих обязательных инструктажей,
              медосмотра и необходимых удостоверений/допусков. Правило применяется автоматически.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
