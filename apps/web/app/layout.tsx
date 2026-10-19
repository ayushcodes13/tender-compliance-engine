import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Tender Review",
    template: "%s · Tender Review",
  },
  description: "Extract technical requirements from a tender and review each one against its cited page.",
  icons: {
    icon: "/tce-mark.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <head />
      <body>{children}</body>
    </html>
  );
}
