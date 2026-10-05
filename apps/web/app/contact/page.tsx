"use client";

import Link from "next/link";
import { motion } from "framer-motion";

import { Footer } from "@/components/sections/faq-footer";
import { LandingNavbar } from "@/components/sections/landing-navbar";

const pilotScope = [
  {
    title: "One workspace per deployment",
    body: "A pilot runs as a single workspace with invite-only access. There is no shared multi-tenant environment.",
  },
  {
    title: "Self-hosted",
    body: "The engine, database, storage, and OCR run in your own deployment. Nothing is hosted for you as part of a pilot.",
  },
  {
    title: "Evidence stays yours",
    body: "Uploads are validated and malware-scanned before processing and stored with immutable versions, so earlier citations keep pointing at the exact document version they came from.",
  },
  {
    title: "Human decisions are explicit",
    body: "OCR warnings, ambiguous terms, and evidence gaps wait for a reviewer. The engine records unresolved rows rather than closing them with a guess.",
  },
];

const readyToShare = [
  "A representative tender document in PDF or DOCX.",
  "The OEM datasheets, test reports, or quotations you would answer with.",
  "Who reviews and signs off a requirement, and what an acceptable citation looks like to you.",
];

export default function ContactPage() {
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
              Private pilot
            </p>
            <h1 className="mt-5 font-display text-4xl font-bold tracking-tight text-text-primary sm:text-5xl">
              Book a pilot
            </h1>
            <p className="mt-6 max-w-2xl text-lg text-text-secondary">
              Pilots are arranged directly rather than self-serve. Each one is a
              single self-hosted workspace sized around one tender process, and
              it ends when you decide it has answered the question you started
              with.
            </p>
          </motion.div>

          <motion.div
            className="mt-12 grid gap-5 sm:grid-cols-2"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
          >
            {pilotScope.map((item) => (
              <div
                key={item.title}
                className="rounded-lg border border-border bg-surface p-5"
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
            className="mt-12 rounded-lg border border-border bg-surface p-6"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.14, ease: [0.16, 1, 0.3, 1] }}
          >
            <h2 className="font-display text-xl font-bold tracking-tight text-text-primary">
              What to have ready
            </h2>
            <ul className="mt-4 space-y-2.5">
              {readyToShare.map((item) => (
                <li key={item} className="flex gap-3 text-sm text-text-secondary">
                  <span aria-hidden="true" className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </motion.div>

          <motion.div
            className="mt-12 border-t border-border pt-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            <h2 className="font-display text-xl font-bold tracking-tight text-text-primary">
              Already have a deployment?
            </h2>
            <p className="mt-3 text-sm text-text-secondary">
              Open your workspace to upload a tender, review extracted
              requirements, and export the compliance sheet.
            </p>
            <Link
              href="/dashboard"
              className="mt-5 inline-block rounded-md bg-accent px-6 py-3 text-sm font-semibold text-background hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              Open the workspace
            </Link>
          </motion.div>
        </div>
      </section>
      <Footer />
    </main>
  );
}