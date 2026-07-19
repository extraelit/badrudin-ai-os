import type { ReactNode } from "react";
import AppShell from "../../components/AppShell";

// Общая оболочка для всех экранов рабочего интерфейса (навигация + верхняя панель).
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
