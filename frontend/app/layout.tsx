import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Badrudin AI OS",
  description: "Цифровая операционная система ООО «Экстра-Элит»",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // Русская локализация интерфейса (ARCHITECTURE.md раздел 18.5)
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
