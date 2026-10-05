"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  FileText,
Gavel,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  Upload,
  X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Documents", href: "/dashboard/documents", icon: FileText },
  { label: "Requirements", href: "/dashboard/requirements", icon: Gavel },
  { label: "Compliance Matrix", href: "/dashboard/matrix", icon: BarChart3 },
  { label: "Evidence", href: "/dashboard/evidence", icon: Upload },
];

export function DashboardLayout({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen bg-background">
      {/* Mobile sidebar backdrop */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex flex-col w-64 border-r border-border bg-surface md:relative",
          "transition-transform duration-300 ease-in-out md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Sidebar header */}
        <div className="flex h-16 items-center justify-between px-4 border-b border-border">
          <Link href="/dashboard" className="flex items-center gap-2 font-semibold">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10">
              <span className="text-lg">🛡️</span>
            </span>
            <span>Tender Compliance</span>
          </Link>
          <button
            className="rounded-lg p-1 text-text-tertiary hover:bg-surface-elevated md:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Workspace selector */}
        <div className="p-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/10 text-xs font-bold text-accent">
              TC
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">
                Private workspace
              </p>
              <p className="text-xs text-text-tertiary">
                Single-customer pilot
              </p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-4 py-2.5 text-sm transition-all",
                  "hover:bg-surface-elevated hover:text-text-primary",
                  isActive
                    ? "bg-accent/10 text-accent border-r-2 border-accent"
                    : "text-text-secondary",
                )}
                onClick={() => setSidebarOpen(false)}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-border">
          <button className="flex w-full items-center gap-3 rounded-lg px-4 py-2.5 text-sm text-text-secondary hover:bg-surface-elevated hover:text-text-primary">
            <LogOut className="h-4 w-4" />
            <span>Sign out</span>
          </button>
        </div>
      </motion.aside>

      {/* Main content */}
      <div className="flex-1 overflow-hidden">
        {/* Topbar */}
        <header className="flex h-16 items-center justify-between border-b border-border bg-surface px-6">
          <div className="flex items-center gap-4">
            <button
              className="rounded-lg p-2 text-text-tertiary hover:bg-surface-elevated md:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar"
            >
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="text-lg font-semibold text-text-primary">
              Dashboard
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <button className="rounded-lg p-2 text-text-tertiary hover:bg-surface-elevated">
              <Plus className="h-4 w-4" />
            </button>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/10 text-xs font-bold text-accent">
              TC
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="h-[calc(100vh-4rem)] overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
