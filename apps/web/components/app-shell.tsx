"use client";

import {
  BarChart3,
  FileText,
  Gavel,
  LayoutGrid,
  MessageCircle,
  Settings,
  Shield,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { href: "/dashboard/documents", label: "Documents", icon: FileText },
  { href: "/dashboard/requirements", label: "Requirements", icon: Gavel },
  { href: "/dashboard/matrix", label: "Compliance Matrix", icon: BarChart3 },
  { href: "/dashboard/evidence", label: "Evidence", icon: Upload },
  { href: "/dashboard/chat", label: "AI Assistant", icon: MessageCircle },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
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
            <small>Source-linked review</small>
          </span>
        </Link>

        <nav className="rail-nav">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active =
              pathname === item.href || pathname.startsWith(item.href + "/");

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
