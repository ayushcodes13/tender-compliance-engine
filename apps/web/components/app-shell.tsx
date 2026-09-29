"use client";

import { FileCheck2, Files, LayoutGrid, Settings2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/", label: "Projects", icon: LayoutGrid },
  { href: "/projects/demo", label: "Review", icon: FileCheck2 },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-frame">
      <aside className="app-rail" aria-label="Product navigation">
        <Link href="/" className="product-mark" aria-label="Tender Compliance Engine">
          <span>TC</span>
        </Link>

        <nav className="rail-nav">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/");

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
          <button className="rail-icon-button" type="button" aria-label="Documents">
            <Files size={19} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <button className="rail-icon-button" type="button" aria-label="Settings">
            <Settings2 size={19} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <div className="profile-dot" aria-label="Devayush Rout">
            DR
          </div>
        </div>
      </aside>

      <main className="app-main">
        <section className="app-surface">{children}</section>
      </main>
    </div>
  );
}
