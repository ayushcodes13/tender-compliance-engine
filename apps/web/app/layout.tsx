import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

// Font pairing sourced from the ui-ux-pro-max skill's "Tech Startup" pairing
// (Space Grotesk for headings, DM Sans for body). Loaded via a runtime
// <link> rather than next/font/google so the build does not depend on
// reaching fonts.googleapis.com at compile time.
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
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
