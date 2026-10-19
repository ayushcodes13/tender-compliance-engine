"use client";

import { LayoutGrid } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// Only destinations that actually render are advertised. The
// /dashboard/documents, /requirements, /matrix and /evidence routes exist but
// are still "coming soon" stubs, so listing them in the rail implied
// functionality the product does not have yet.
const navigation = [
  { href: "/dashboard", label: "Projects", icon: LayoutGrid },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-frame">
      <aside className="app-rail" aria-label="Product navigation">
        <Link
          href="/dashboard"
          className="product-brand"
          aria-label="Tender Compliance Engine"
        >
          <span className="product-mark">
            <img src="/tce-mark.svg" alt="" width="30" height="30" />
          </span>
          <span className="product-brand-copy">
            <strong>Tender Compliance</strong>
            <small>Single-user tender pilot</small>
          </span>
        </Link>

        <nav className="rail-nav">
          {navigation.map((item) => {
            const Icon = item.icon;
            // Projects stays active inside a project: the project pages are
            // reached by drilling into a project from this list, so they are
            // not separate top-level destinations.
            const active =
              pathname === item.href ||
              pathname.startsWith(item.href + "/") ||
              pathname.startsWith("/projects");

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
          <div
            className="workspace-chip"
            aria-label="Single workspace private pilot"
          >
            <div className="profile-dot">TC</div>
            <div>
              <strong>Your private workspace</strong>
              <span>Single-operator pilot</span>
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
