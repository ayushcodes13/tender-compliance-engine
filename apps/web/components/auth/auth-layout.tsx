"use client";

/*
  Auth pages — sign-in and sign-up.
  Shared layout with a frosted-glass accent panel and a form card.
*/

import Link from "next/link";
import { motion } from "framer-motion";

import { AuthForm, type AuthMode } from "@/components/auth/auth-form";
import { cn } from "@/lib/utils";

const pageVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};

export default function AuthLayout({
  mode,
}: {
  mode: AuthMode;
}) {
  const title = mode === "sign-in" ? "Welcome back" : "Create your account";
  const subtitle =
    mode === "sign-in"
      ? "Sign in to continue to Tender Compliance Engine"
      : "Private pilot access. Self-hosted, single workspace.";
  const otherHref = mode === "sign-in" ? "/sign-up" : "/sign-in";
  const otherLabel =
    mode === "sign-in" ? "Don't have an account?" : "Already have an account?";

  return (
    <main
      className={cn(
        "flex min-h-screen items-center justify-center bg-background",
        "px-6 py-12 md:py-0",
      )}
    >
      <motion.div
        className="w-full max-w-5xl overflow-hidden rounded-2xl border border-border"
        initial="initial"
        animate="animate"
        exit="exit"
        variants={pageVariants}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] as const }}
      >
        <div className="flex flex-col md:flex-row">
          {/* Accent panel — frosted glass, theme logo, no orbs/emoji */}
          <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden rounded-2xl border border-white/12 bg-white/[0.03] p-12 text-center backdrop-blur-xl">
            <div className="mb-6 flex h-12 w-12 items-center justify-center">
              <img
                src="/tce-mark.svg"
                alt=""
                width={36}
                height={36}
                className="h-auto w-9"
              />
            </div>
            <h2 className="font-display text-2xl font-bold text-text-primary">
              Tender Compliance Engine
            </h2>
            <p className="mt-3 max-w-xs text-sm text-text-secondary">
              Your compliance decisions, traceable to the source document.
            </p>
          </div>

          {/* Form panel */}
          <div className="flex-1 p-10">
            <h1 className="font-display text-2xl font-bold text-text-primary">
              {title}
            </h1>
            <p className="mt-2 text-sm text-text-secondary">{subtitle}</p>

            <div className="mt-8">
              <AuthForm mode={mode} />
            </div>

            <div className="mt-6 text-center text-xs text-text-tertiary">
              {otherLabel}{" "}
              <Link
                href={otherHref}
                className="font-medium text-accent hover:text-accent-hover"
              >
                {mode === "sign-in" ? "Sign up" : "Sign in"}
              </Link>
            </div>
          </div>
        </div>
      </motion.div>
    </main>
  );
}
