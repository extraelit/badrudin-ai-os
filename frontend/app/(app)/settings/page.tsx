"use client";

/* Экран 11. Настройки (интерактивные разделы и переключатели). */
import { useState } from "react";
import { PageHead, Card, Badge, Risk } from "../../../components/ui";
import { settingsSections, integrations, company } from "../../../lib/mock";

export default function SettingsPage() {
  const [active, setActive] = useState("profile");
  const [toggles, setToggles] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(integrations.map((i) => [i.name, i.on]))
  );
  const [notif, setNotif] = useState({ email: true, telegram: true, digest: true, escalation: false });

  return (
    <>
      <PageHead title="Настройки" desc="Профиль, безопасность, уведомления, ИИ-агенты и интеграции" />

      <div className="grid" style={{ gridTemplateColumns: "240px 1fr", gap: 18, alignItems: "start" }}>
        <Card flush>
          <div className="list">
            {settingsSections.map((s) => (
              <button
                key={s.key}
                onClick={() => setActive(s.key)}
                className={`navlink${active === s.key ? " navlink--active" : ""}`}
                style={{
                  color: active === s.key ? "var(--navy-700)" : "var(--graphite-700)",
                  background: active === s.key ? "var(--navy-50)" : "transparent",
                  border: "none",
                  textAlign: "left",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  borderRadius: 0,
                }}
              >
                {s.title}
              </button>
            ))}
          </div>
        </Card>

        <div>
          {active === "profile" && (
            <Card title="Профиль и организация">
              <div className="grid grid--2" style={{ gap: 16 }}>
                <div className="field">
                  <label>Организация</label>
                  <input defaultValue={company.name} />
                </div>
                <div className="field">
                  <label>Руководитель</label>
                  <input defaultValue="Бадрудин М." />
                </div>
                <div className="field">
                  <label>Электронная почта</label>
                  <input defaultValue="director@extra-elit.demo" />
                </div>
                <div className="field">
                  <label>Язык интерфейса</label>
                  <select defaultValue="ru">
                    <option value="ru">Русский</option>
                    <option value="en">English</option>
                  </select>
                </div>
              </div>
              <button className="btn btn--primary btn--sm">Сохранить изменения</button>
            </Card>
          )}

          {active === "security" && (
            <Card title="Безопасность и доступ">
              <div className="toggle">
                <div>
                  <div className="table__strong">Многофакторная аутентификация (MFA)</div>
                  <div className="muted" style={{ fontSize: 12.5 }}>Обязательна для критических ролей и действий R4</div>
                </div>
                <Badge tone="emerald">Включена</Badge>
              </div>
              <div className="toggle">
                <div>
                  <div className="table__strong">Уровень подтверждения действий</div>
                  <div className="muted" style={{ fontSize: 12.5 }}>Действия R3/R4 требуют подтверждения человека</div>
                </div>
                <div className="row" style={{ gap: 4 }}>
                  <Risk level="R3" /><Risk level="R4" />
                </div>
              </div>
              <div className="toggle">
                <div>
                  <div className="table__strong">Журнал аудита</div>
                  <div className="muted" style={{ fontSize: 12.5 }}>Неизменяемая запись критических действий</div>
                </div>
                <Badge tone="navy">Активен</Badge>
              </div>
            </Card>
          )}

          {active === "notifications" && (
            <Card title="Уведомления">
              {[
                { key: "email", title: "Уведомления по электронной почте", sub: "Официальная рассылка поручений" },
                { key: "telegram", title: "Уведомления в Telegram", sub: "Оперативные события с объектов" },
                { key: "digest", title: "Ежедневная сводка", sub: "Утренний и вечерний отчёт директору" },
                { key: "escalation", title: "Экстренные эскалации", sub: "Критические риски и просрочки" },
              ].map((n) => (
                <div className="toggle" key={n.key}>
                  <div>
                    <div className="table__strong">{n.title}</div>
                    <div className="muted" style={{ fontSize: 12.5 }}>{n.sub}</div>
                  </div>
                  <div
                    className={`switch${notif[n.key as keyof typeof notif] ? " switch--on" : ""}`}
                    onClick={() => setNotif((p) => ({ ...p, [n.key]: !p[n.key as keyof typeof notif] }))}
                    role="switch"
                    aria-checked={notif[n.key as keyof typeof notif]}
                  />
                </div>
              ))}
            </Card>
          )}

          {active === "agents" && (
            <Card title="ИИ-агенты и режимы">
              <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
                Режим по умолчанию определяет, может ли агент действовать самостоятельно
                или готовит решение на согласование. Критические действия всегда через человека.
              </div>
              <div className="field">
                <label>Режим по умолчанию для новых агентов</label>
                <select defaultValue="prepare">
                  <option value="advice">Только рекомендация</option>
                  <option value="prepare">Подготовка на согласование</option>
                  <option value="send">Отправка после утверждения</option>
                  <option value="auto">Разрешённая автоматизация</option>
                </select>
                <span className="field__hint">Применяется ко вновь подключаемым агентам.</span>
              </div>
              <div className="toggle">
                <div>
                  <div className="table__strong">Независимый ИИ-аудитор</div>
                  <div className="muted" style={{ fontSize: 12.5 }}>Проверяет результаты агентов до передачи руководителю</div>
                </div>
                <div className="switch switch--on" role="switch" aria-checked />
              </div>
            </Card>
          )}

          {active === "integrations" && (
            <Card title="Интеграции" flush>
              <div className="list">
                {integrations.map((i) => (
                  <div className="list__item" key={i.name}>
                    <div className="list__main">
                      <div className="list__title">{i.name}</div>
                      <div className="list__sub">{i.desc}</div>
                    </div>
                    <div
                      className={`switch${toggles[i.name] ? " switch--on" : ""}`}
                      onClick={() => setToggles((p) => ({ ...p, [i.name]: !p[i.name] }))}
                      role="switch"
                      aria-checked={toggles[i.name]}
                    />
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      <div className="alert" style={{ marginTop: 18 }}>
        <div className="alert__icon">ℹ</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Демонстрационный режим: настройки не сохраняются на сервере, реальные
          секреты и подключение к production отсутствуют.
        </div>
      </div>
    </>
  );
}
