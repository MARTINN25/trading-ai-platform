import type { Metadata } from "next";
import type { ReactNode } from "react";

import AppShell from "@/components/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Trading Assistant Platform",
  description: "AI Trading Assistant Platform",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="ru">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
