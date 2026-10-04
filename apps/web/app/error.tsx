"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <AppShell>
      <div className="page-scroll">
        <div className="page-container">
          <div className="product-error">
            <AlertTriangle size={30} aria-hidden="true" />
            <h1>We could not load this workspace.</h1>
            <p>{error.message || "The request failed unexpectedly."}</p>
            <div className="inline-actions">
              <button className="button button-primary" type="button" onClick={reset}>
                <RefreshCw size={14} aria-hidden="true" /> Try again
              </button>
              <Link href="/" className="button button-secondary">Back to projects</Link>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
