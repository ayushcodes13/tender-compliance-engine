"use client";

import Link from "next/link";
import { motion } from "framer-motion";

import { faqs, footerColumns, footerCopyright } from "@/lib/data/landing";

export function FaqSection() {
  return (
    <section id="faq" className="landing-section-premium w-full border-t border-border bg-background py-20 md:py-28">
      <div className="container mx-auto px-6 md:px-8">
        <motion.div
          className="mb-14 text-center"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] as const }}
        >
          <h2 className="font-display text-3xl text-text-primary sm:text-4xl">
            Questions
          </h2>
        </motion.div>

        <motion.div
          className="mx-auto max-w-3xl space-y-3"
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, amount: 0.2 }}
          variants={{
            animate: {
              transition: { staggerChildren: 0.06, delayChildren: 0.05 },
            },
          }}
        >
          {faqs.map((faq) => (
            <FaqItem key={faq.question} question={faq.question} answer={faq.answer} />
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function FaqItem({ question, answer }: { question: string; answer: string }) {
  return (
    <motion.div
      className="premium-faq-item"
      variants={{
        initial: { opacity: 0, y: 10 },
        animate: { opacity: 1, y: 0 },
      }}
      transition={{
        duration: 0.4,
        ease: [0.16, 1, 0.3, 1] as const,
      }}
    >
      <h3 className="text-lg font-semibold text-text-primary">
        {question}
      </h3>
      <p className="mt-2 text-sm text-text-secondary">{answer}</p>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/* Footer                                                             */
/* ------------------------------------------------------------------ */

export function Footer() {
  return (
    <footer className="premium-footer w-full border-t border-border bg-surface py-12">
      <div className="container mx-auto px-6 md:px-8">
        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">
          {/* Brand */}
          <div className="lg:col-span-2">
            <Link href="/" className="landing-brand flex items-center gap-2">
              <img
                src="/tce-mark.svg"
                alt=""
                width={34}
                height={34}
                className="h-8 w-8"
              />
              <span>Tender Compliance Engine</span>
            </Link>
            <p className="mt-3 max-w-sm text-sm text-text-secondary">
              Turn tender documents and OEM evidence into a source-linked,
              human-reviewable compliance sheet.
            </p>
          </div>

          {/* Columns */}
          {footerColumns.map((col) => (
            <div key={col.title}>
              <h4 className="text-sm font-semibold text-text-primary">
                {col.title}
              </h4>
              <ul className="mt-3 space-y-2">
                {col.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-text-secondary hover:text-text-primary"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <motion.div
          className="mt-12 border-t border-border/50 pt-6 text-center text-sm text-text-tertiary"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
        >
          {footerCopyright}
        </motion.div>
      </div>
    </footer>
  );
}
