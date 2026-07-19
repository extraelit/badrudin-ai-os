"use client";

/*
 * Защита маршрутов рабочего интерфейса.
 * При настроенном backend (NEXT_PUBLIC_API_BASE_URL) проверяет сессию через
 * /auth/me и перенаправляет на /login, если пользователь не авторизован.
 * Если backend не настроен — демонстрационный режим (mock), доступ открыт.
 */
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiBaseConfigured, getToken, me } from "../lib/authApi";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const live = apiBaseConfigured();
  const [ready, setReady] = useState(!live); // в демо-режиме сразу готово

  useEffect(() => {
    if (!live) return;
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    me()
      .then(() => setReady(true))
      .catch(() => router.replace("/login"));
  }, [live, pathname, router]);

  if (!ready) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
        <div className="muted">Проверка сессии…</div>
      </div>
    );
  }
  return <>{children}</>;
}
