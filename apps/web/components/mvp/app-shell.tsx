"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, FilePlus2, LayoutDashboard, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

export function AppShell({ active, children }: { active: "dashboard" | "new" | "method"; children: ReactNode }) {
  const items = [
    { key: "dashboard" as const, href: "/dashboard", label: "Overview", Icon: LayoutDashboard },
    { key: "new" as const, href: "/new", label: "New review", Icon: FilePlus2 },
    { key: "method" as const, href: "/method", label: "How it works", Icon: BookOpen },
  ];
  return <div className="app-shell">
    <aside className="app-sidebar">
      <Link href="/" className="app-brand"><span className="app-brand-mark">T</span><span><strong>Tender Review</strong><small>Technical workspace</small></span></Link>
      <div className="app-nav-label">WORKSPACE</div>
      <nav aria-label="Workspace">
        {items.map(({key,href,label,Icon}) => <Link key={key} href={href} className={active===key?"app-nav-link is-active":"app-nav-link"}><Icon size={17}/>{label}{key==="new"&&<ArrowRight className="app-nav-arrow" size={14}/>}</Link>)}
      </nav>
      <div className="app-sidebar-bottom"><ShieldCheck size={16}/><span><strong>Private session</strong><small>Documents are not saved</small></span></div>
    </aside>
    <div className="app-main">
      <header className="app-topbar">
        <div className="app-breadcrumb"><span>Workspace</span><b>/</b><strong>{items.find(item=>item.key===active)?.label}</strong></div>
        <span className="app-session-pill"><i/>Single-user demo</span>
      </header>
      {children}
    </div>
  </div>;
}
