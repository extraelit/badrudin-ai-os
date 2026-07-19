"use client";

/*
 * Экран входа Badrudin AI OS.
 * Реальная аутентификация через backend (/auth/login) с сохранением JWT.
 * Если backend не настроен (NEXT_PUBLIC_API_BASE_URL пуст) — показывается
 * демонстрационный вход в интерфейс с mock-данными (без аутентификации).
 */
import { useRouter } from "next/navigation";
import { useState } from "react";
import { login, apiBaseConfigured } from "../../lib/authApi";

export default function LoginPage() {
  const router = useRouter();
  const live = apiBaseConfigured();
  const [email, setEmail] = useState("director@extra-elit.demo");
  const [password, setPassword] = useState("");
  const [mfa, setMfa] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function enter(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!live) {
      router.push("/dashboard");
      return;
    }
    setBusy(true);
    try {
      await login(email, password, mfa || undefined);
      router.push("/dashboard");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Ошибка входа";
      setError(msg.toLowerCase().includes("mfa") || msg.toLowerCase().includes("многофактор") ? "Требуется код MFA" : msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login__side">
        <div className="login__brand">
          <div className="login__logo">B</div>
          <div>
            <div className="login__brand-title">Badrudin AI OS</div>
            <div className="login__brand-sub">ООО «Экстра-Элит»</div>
          </div>
        </div>
        <div className="login__hero">
          <h2>Единый цифровой центр управления компанией</h2>
          <p>
            Объекты, задачи, финансы, снабжение, документы и ИИ-агенты — в одном
            интерфейсе. Человек принимает окончательное решение.
          </p>
          <ul className="login__list">
            <li>Согласование критических действий по шкале R0–R4</li>
            <li>Контроль сроков и просрочек в реальном времени</li>
            <li>ИИ готовит — руководитель утверждает</li>
          </ul>
        </div>
        <div className="login__foot">
          {live ? "Рабочий режим · вход через backend" : "Демонстрационная версия · показ интерфейса на mock-данных"}
        </div>
      </div>

      <div className="login__main">
        <form className="login__form" onSubmit={enter}>
          <h1>Вход в систему</h1>
          <p className="muted" style={{ marginTop: 4, marginBottom: 22 }}>
            Введите рабочую учётную запись
          </p>

          <div className="field">
            <label>Электронная почта</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
          </div>
          <div className="field">
            <label>Пароль</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </div>
          {live && (
            <div className="field">
              <label>Код MFA (для критических ролей)</label>
              <input type="text" value={mfa} onChange={(e) => setMfa(e.target.value)} placeholder="необязательно" inputMode="numeric" />
            </div>
          )}

          {error && (
            <div className="alert" style={{ marginBottom: 14 }}>
              <div className="alert__icon">!</div>
              <div style={{ fontSize: 13 }}>{error}</div>
            </div>
          )}

          <button type="submit" className="btn btn--primary" disabled={busy} style={{ width: "100%", justifyContent: "center" }}>
            {busy ? "Вход…" : "Войти в систему"}
          </button>

          <div className="login__note">
            {live
              ? "Демо-учётные записи: director@extra-elit.demo (директор) · owner@extra-elit.demo (владелец, требует MFA). Пароль — из SEED_DEMO_PASSWORD."
              : "Демо-режим: backend не подключён. Кнопка открывает интерфейс с демонстрационными данными."}
          </div>
        </form>
      </div>
    </div>
  );
}
