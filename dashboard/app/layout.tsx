import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "AEGIS — Autonomous Financial-Crime Investigation Mesh",
  description: "Adversarial multi-agent AML investigation, governed on Band.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
