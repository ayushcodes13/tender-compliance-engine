import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Tender Compliance Engine",
    template: "%s · Tender Compliance Engine",
  },
  description:
    "Turn tender requirements and OEM evidence into a source-linked, reviewable compliance sheet.",
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
