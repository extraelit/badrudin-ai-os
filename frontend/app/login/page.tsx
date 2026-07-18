"use client";

import { useEffect, useState } from "react";

// Базовый URL backend берётся из переменной окружения (D-008)
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type HealthStatus = "проверка…" | "доступен" | "недоступен";

export default function LoginPage() {
  const [backendStatus, setBackendStatus] = useState<HealthStatus>("проверка…");

  useEffect(() => {
    // Запрос health-check backend (T-1.A4)
    fetch(`${API_BASE_URL}/health`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then(() => setBackendStatus("доступен"))
      .catch(() => setBackendStatus("недоступен"));
  }, []);

  return (
    <main style={{ maxWidth: 360, margin: "80px auto", fontFamily: "sans-serif" }}>
      <h1>Badrudin AI OS</h1>
      <p>Вход в систему</p>

      {/* Заглушка формы входа; аутентификация реализуется в задаче T-1.C1 */}
      <form onSubmit={(e) => e.preventDefault()}>
        <label>
          Электронная почта
          <input type="email" name="email" autoComplete="username" disabled />
        </label>
        <label>
          Пароль
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            disabled
          />
        </label>
        <button type="submit" disabled>
          Войти (доступно после T-1.C1)
        </button>
      </form>

      <p>Состояние backend: {backendStatus}</p>
    </main>
  );
}
