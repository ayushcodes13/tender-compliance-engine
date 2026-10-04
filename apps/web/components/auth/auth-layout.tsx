"use client";

/*
  Auth pages — sign-in and sign-up.
  Shared layout with a gradient accent panel and a form card.
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
      : "Start your 14-day free trial. No credit card required.";
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
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="flex flex-col md:flex-row">
          {/* Accent panel */}
          <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden bg-gradient-to-br from-accent/20 via-accent/5 to-background p-12 text-center">
            <div
              className="absolute inset-0 pointer-events-none"
              aria-hidden="true"
            >
              <div className="absolute -top-32 -left-16 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
              <div className="absolute -bottom-32 -right-16 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
            </div>
            <div className="relative z-10">
              <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-accent/10 text-2xl">
                🛡️
              </div>
              <h2 className="font-display text-2xl font-bold text-text-primary">
                Tender Compliance Engine
              </h2>
              <p className="mt-3 max-w-xs text-sm text-text-secondary">
                Your compliance decisions, traceable to the source document.
              </p>
            </div>
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
