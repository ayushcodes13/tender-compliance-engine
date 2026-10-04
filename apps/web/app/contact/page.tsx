"use client";

import { LandingNavbar } from "@/components/sections/landing-navbar";
import { Footer } from "@/components/sections/faq-footer";
import { motion } from "framer-motion";

export default function ContactPage() {
  return (
    <main>
      <LandingNavbar />
      <section className="py-20">
        <div className="container mx-auto max-w-2xl px-6 md:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <h1 className="font-display text-4xl font-bold tracking-tight text-text-primary">
              Get in touch
            </h1>
            <p className="mt-4 text-lg text-text-secondary">
              Have questions about the Tender Compliance Engine? Reach out and
              we'll get back to you.
            </p>
          </motion.div>

          <motion.form
            className="mt-10 space-y-5"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-text-secondary">
                  Name
                </label>
                <input
                  type="text"
                  required
                  className="mt-1 w-full rounded-lg border border-border bg-surface-elevated px-4 py-2.5 text-sm text-text-primary focus:ring-2 focus:ring-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-secondary">
                  Email
                </label>
                <input
                  type="email"
                  required
                  className="mt-1 w-full rounded-lg border border-border bg-surface-elevated px-4 py-2.5 text-sm text-text-primary focus:ring-2 focus:ring-accent focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary">
                Subject
              </label>
              <input
                type="text"
                required
                className="mt-1 w-full rounded-lg border border-border bg-surface-elevated px-4 py-2.5 text-sm text-text-primary focus:ring-2 focus:ring-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary">
                Message
              </label>
              <textarea
                rows={5}
                required
                className="mt-1 w-full rounded-lg border border-border bg-surface-elevated px-4 py-2.5 text-sm text-text-primary focus:ring-2 focus:ring-accent focus:outline-none"
              />
            </div>
            <motion.button
              type="submit"
              className="w-full rounded-full bg-accent px-6 py-3 text-sm font-semibold text-background hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent"
              whileHover={{ scale: 1.02 }}
              transition={{ duration: 0.15 }}
            >
              Send message
            </motion.button>
          </motion.form>
        </div>
      </section>
      <Footer />
    </main>
  );
}
