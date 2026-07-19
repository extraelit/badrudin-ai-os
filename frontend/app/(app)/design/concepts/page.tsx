/* Модуль «Проектирование и дизайн». Экран 4 — концепции и версии. */
import { PageHead, Card, Badge } from "../../../../components/ui";
import { Icons } from "../../../../lib/icons";
import { concepts } from "../../../../lib/design";

export default function ConceptsPage() {
  return (
    <>
      <PageHead
        title="Концепции и версии"
        desc="Дизайн-концепции, версии и обратная связь заказчика"
        action={<button className="btn btn--primary btn--sm"><Icons.plus width={16} height={16} /> Новая концепция</button>}
      />

      <div className="grid grid--3">
        {concepts.map((c) => (
          <div key={c.name} className="card">
            <div className="card__body">
              <div style={{ height: 120, borderRadius: 10, background: "linear-gradient(135deg,var(--navy-100),var(--graphite-200))", marginBottom: 14, display: "flex", alignItems: "flex-end", padding: 10 }}>
                <span style={{ fontSize: 11, color: "var(--graphite-700)", background: "rgba(255,255,255,.85)", borderRadius: 5, padding: "2px 6px" }}>Превью (демо)</span>
              </div>
              <div className="row row--between" style={{ marginBottom: 6 }}>
                <span className="badge badge--gray">версия {c.version}</span>
                <Badge tone={c.statusTone}>{c.status}</Badge>
              </div>
              <div className="list__title">{c.name}</div>
              <div className="list__sub" style={{ marginBottom: 10 }}>Автор: {c.author}</div>
              <div className="divider" />
              <div className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>{c.feedback}</div>
              <div className="row" style={{ gap: 8, marginTop: 12 }}>
                <button className="btn btn--ghost btn--sm">Новая версия</button>
                <button className="btn btn--ghost btn--sm">История</button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ height: 18 }} />
      <div className="alert">
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Версии концепций и презентаций хранятся через документооборот (files / document_versions);
          утверждение концепции заказчиком — уровень R2 с фиксацией в аудите.
        </div>
      </div>
    </>
  );
}
