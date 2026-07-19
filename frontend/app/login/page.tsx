"use client";

/*
 * Демонстрационный экран входа (UX/UI-прототип).
 * Аутентификация не выполняется: кнопка ведёт в демо-интерфейс с mock-данными.
 * Реальные учётные данные, секреты и подключение к production отсутствуют.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("director@extra-elit.demo");
  const [password, setPassword] = useState("demo-2026");

  function enter(e: React.FormEvent) {
    e.preventDefault();
    router.push("/dashboard");
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
          Демонстрационная версия · показ интерфейса на mock-данных
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
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
            />
          </div>
          <div className="field">
            <label>Пароль</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>

          <div className="row row--between" style={{ margin: "6px 0 20px" }}>
            <label className="row" style={{ gap: 8, fontSize: 13 }}>
              <input type="checkbox" defaultChecked /> Запомнить меня
            </label>
            <span className="link-more">Забыли пароль?</span>
          </div>

          <button type="submit" className="btn btn--primary" style={{ width: "100%", justifyContent: "center" }}>
            Войти в систему
          </button>

          <div className="login__note">
            Демо-режим: аутентификация и production не подключены. Кнопка
            открывает интерфейс с демонстрационными данными.
          </div>
        </form>
      </div>
    </div>
  );
}
