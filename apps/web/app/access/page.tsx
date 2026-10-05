"use client";

import Link from "next/link";
import { motion } from "framer-motion";

import { Footer } from "@/components/sections/faq-footer";
import { LandingNavbar } from "@/components/sections/landing-navbar";

const facts = [
  {
    title: "There is no account to create",
    body: "A pilot deployment runs as a single workspace with one owner identity configured at deploy time. Signing up here would create a second, disconnected account.",
  },
  {
    title: "There is no password to choose",
    body: "The engine resolves who you are from the deployment configuration, not from a credential you type into this page.",
  },
  {
    title: "Access is granted by whoever runs it",
    body: "A private pilot is normally reached over a VPN, behind your identity provider, or on a private network. This application does not implement its own login.",
  },
];

export default function AccessPage() {
  return (
    <main>
      <LandingNavbar />
      <section className="w-full py-20 md:py-28">
        <div className="container mx-auto max-w-3xl px-6 md:px-8">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="text-xs font-semibold uppercase tracking-wider text-accent">
              Access
            </p>
            <h1 className="mt-5 font-display text-4xl font-bold tracking-tight text-text-primary sm:text-5xl">
              This pilot has no sign-up
            </h1>
            <p className="mt-6 max-w-2xl text-lg text-text-secondary">
              We removed the login form rather than ship one that does nothing.
              It accepted any email and password, showed a loading spinner, and
              dropped you into the workspace. Anyone could reach your tender
              documents through it.
            </p>
          </motion.div>

          <motion.div
            className="mt-12 grid gap-5 sm:grid-cols-3"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
          >
            {facts.map((item) => (
              <div
                key={item.title}
                className="border-t border-border pt-5"
              >
                <h2 className="text-sm font-semibold text-text-primary">
                  {item.title}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                  {item.body}
                </p>
              </div>
            ))}
          </motion.div>

          <motion.div
            className="mt-12 border-t border-border pt-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.14 }}
          >
            <h2 className="font-display text-xl font-bold tracking-tight text-text-primary">
              If you already have a deployment
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              Reach the workspace on the address your pilot operator gave you.
              If that address is this one, your session is already
              authenticated by whatever sits in front of the application.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link
                href="/dashboard"
                className="rounded-md bg-accent px-6 py-3 text-sm font-semibold text-white hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                Open the workspace
              </Link>
              <Link
                href="/contact"
                className="rounded-md border border-border px-6 py-3 text-sm font-semibold text-text-primary hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                Request access
              </Link>
            </div>
          </motion.div>
        </div>
      </section>
      <Footer />
    </main>
  );
}