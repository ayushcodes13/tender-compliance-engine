"use client";

import { LayoutGrid } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/", label: "Projects", icon: LayoutGrid },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-frame">
      <aside className="app-rail" aria-label="Product navigation">
        <Link href="/" className="product-brand" aria-label="Tender Compliance Engine">
          <span className="product-mark">
            <img src="/tce-mark.svg" alt="" width="30" height="30" />
          </span>
          <span className="product-brand-copy">
            <strong>Tender Compliance</strong>
            <small>Source-linked review</small>
          </span>
        </Link>

        <nav className="rail-nav">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/"
                ? pathname === "/" || pathname.startsWith("/projects/")
                : pathname === item.href || pathname.startsWith(item.href + "/");

            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "rail-link rail-link-active" : "rail-link"}
                aria-current={active ? "page" : undefined}
              >
                <Icon size={21} strokeWidth={1.8} aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="rail-footer">
          <div className="workspace-chip" aria-label="Single workspace private pilot">
            <div className="profile-dot">TC</div>
            <div>
              <strong>Private workspace</strong>
              <span>Single-customer pilot</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="app-main">
        <section className="app-surface">{children}</section>
      </main>
    </div>
  );
}
