import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { ServiceWorkerRegister } from "../components/ServiceWorkerRegister";

export const metadata: Metadata = {
  title: "Badrudin AI OS — цифровая операционная система",
  description: "Цифровая операционная система ООО «Экстра-Элит»",
  applicationName: "Badrudin AI OS",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Badrudin", statusBarStyle: "black-translucent" },
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#0b1220",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // Русская локализация интерфейса (ARCHITECTURE.md раздел 18.5)
  return (
    <html lang="ru">
      <body>
        {children}
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
