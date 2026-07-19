import type { ReactNode } from "react";
import AppShell from "../../components/AppShell";
import AuthGuard from "../../components/AuthGuard";

// Общая оболочка для всех экранов рабочего интерфейса (навигация + верхняя панель).
// AuthGuard защищает маршруты: при настроенном backend требуется вход.
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
