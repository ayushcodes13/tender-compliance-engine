"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

const formVariants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
};

export type AuthMode = "sign-in" | "sign-up";

interface AuthFormProps {
  mode: AuthMode;
}

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    // Simulate auth, then redirect to dashboard
    setTimeout(() => {
      router.push("/dashboard");
    }, 800);
  };

  const otherMode = mode === "sign-in" ? "sign-up" : "sign-in";
  const otherLabel = mode === "sign-in" ? "Sign up" : "Sign in";

  return (
    <AnimatePresence mode="wait">
      <motion.form
        key={mode}
        variants={formVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="w-full space-y-5"
        onSubmit={handleSubmit}
      >
        {mode === "sign-up" && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            <label className="block text-sm font-medium text-text-secondary">
              Full name
            </label>
            <input
              type="text"
              placeholder="Jane Doe"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className={cn(
                "mt-1 w-full rounded-lg border border-border bg-surface-elevated",
                "px-4 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary",
                "focus:ring-2 focus:ring-accent focus:outline-none",
              )}
            />
          </motion.div>
        )}

        <div>
          <label className="block text-sm font-medium text-text-secondary">
            Email
          </label>
          <input
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className={cn(
              "mt-1 w-full rounded-lg border border-border bg-surface-elevated",
              "px-4 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary",
              "focus:ring-2 focus:ring-accent focus:outline-none",
            )}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-text-secondary">
            Password
          </label>
          <input
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            className={cn(
              "mt-1 w-full rounded-lg border border-border bg-surface-elevated",
              "px-4 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary",
              "focus:ring-2 focus:ring-accent focus:outline-none",
            )}
          />
        </div>

        <div className="pt-1">
          <motion.button
            type="submit"
            disabled={loading || !email || !password}
            className={cn(
              "w-full rounded-md bg-accent py-2.5 text-sm font-semibold text-background",
              "hover:bg-accent-hover disabled:opacity-60",
              "focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background",
              "transition-colors",
            )}
            whileHover={{ scale: 1.02 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg
                  className="h-4 w-4 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                </svg>
                {mode === "sign-in" ? "Signing in…" : "Creating account…"}
              </span>
            ) : mode === "sign-in" ? (
              "Sign in"
            ) : (
              "Create account"
            )}
          </motion.button>
        </div>

        <div className="text-center text-sm text-text-secondary">
          Already have an account?{" "}
          <Link
            href={`/sign-${otherMode}`}
            className="font-medium text-accent hover:text-accent-hover"
          >
            {otherLabel}
          </Link>
        </div>
      </motion.form>
    </AnimatePresence>
  );
}
