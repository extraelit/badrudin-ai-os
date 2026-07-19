/* Модуль «Проектирование и дизайн». Экран 3 — техническое задание / бриф. */
import { PageHead, Card, Badge, Risk } from "../../../../components/ui";
import { brief } from "../../../../lib/design";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="kpi__label" style={{ marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 14, color: "var(--graphite-800)" }}>{value}</div>
    </div>
  );
}

export default function BriefPage() {
  return (
    <>
      <PageHead
        title="Техническое задание / бриф"
        desc="Требования заказчика, функциональные и стилевые требования, бюджет и срок"
        action={
          <div className="row" style={{ gap: 8 }}>
            <Badge tone={brief.statusTone}>{brief.status}</Badge>
            <button className="btn btn--ghost btn--sm">Редактировать</button>
          </div>
        }
      />

      <div className="grid grid--3" style={{ gap: 18 }}>
        <Card title={brief.title} className="span-2">
          <Field label="Заказчик" value={brief.client} />
          <div className="divider" style={{ margin: "4px 0 16px" }} />
          <Field label="Функциональные требования" value={brief.functional} />
          <Field label="Стилевые предпочтения" value={brief.style} />
          <div className="grid grid--2" style={{ gap: 16 }}>
            <Field label="Диапазон бюджета" value={brief.budget} />
            <Field label="Плановый срок" value={brief.target} />
          </div>
        </Card>

        <div className="stack">
          <Card title="Статус согласования">
            <div className="toggle"><span className="muted">Текущий статус</span><Badge tone={brief.statusTone}>{brief.status}</Badge></div>
            <div className="toggle"><span className="muted">Уровень действия</span><Risk level="R2" /></div>
            <div className="row" style={{ marginTop: 14 }}>
              <button className="btn btn--emerald btn--sm" disabled={brief.status === "Утверждено"}>Утвердить ТЗ</button>
            </div>
            <div className="field__hint" style={{ marginTop: 10 }}>
              Утверждение ТЗ — уровень R2 (человек в контуре). Изменения фиксируются в аудите.
            </div>
          </Card>
          <Card title="Связанные документы" flush>
            <div className="list">
              <div className="list__item"><div className="list__main"><div className="list__title" style={{ fontSize: 13 }}>Исходные данные (комплект)</div><div className="list__sub">documents · проверено ГИП</div></div><Badge tone="emerald">✓</Badge></div>
              <div className="list__item"><div className="list__main"><div className="list__title" style={{ fontSize: 13 }}>Задание на проектирование</div><div className="list__sub">documents · v2</div></div><Badge tone="navy">v2</Badge></div>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
