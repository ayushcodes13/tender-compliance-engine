"use client";

import Link from "next/link";
import { motion } from "framer-motion";

import { heroData } from "@/lib/data/landing";

const container = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: {
      duration: 0.5,
      ease: [0.16, 1, 0.3, 1] as const,
      staggerChildren: 0.08,
      delayChildren: 0.05,
    },
  },
};

const item = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
};

export function HeroSection() {
  return (
    <section className="landing-hero w-full border-b border-border bg-background py-24 md:py-32">
      <motion.div
        className="container mx-auto flex justify-center px-6 text-center md:px-8"
        variants={container}
        initial="initial"
        animate="animate"
      >
        <motion.div
          className="landing-hero-card w-full max-w-5xl px-6 py-12 text-center md:px-12 md:py-16"
          variants={item}
        >
          <motion.p
            className="premium-eyebrow text-accent"
            variants={item}
          >
            {heroData.eyebrow}
          </motion.p>

          <motion.h1
            className="landing-hero-title mx-auto mt-6 max-w-4xl font-display text-text-primary"
            style={{ lineHeight: 1.1 }}
            variants={item}
          >
            {heroData.headline}
          </motion.h1>

          <motion.p
            className="mx-auto mt-6 max-w-2xl text-lg text-text-secondary"
            style={{ lineHeight: 1.6 }}
            variants={item}
          >
            {heroData.subhead}
          </motion.p>

          <motion.div
            className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row"
            variants={item}
          >
            <motion.div
              variants={item}
              whileHover={{ scale: 1.02 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
            >
              <Link
                href="/contact"
                className="landing-pill-cta inline-flex items-center bg-accent px-7 py-3 text-sm font-semibold text-white hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                {heroData.primaryCta}
              </Link>
            </motion.div>
            <motion.div
              variants={item}
              whileHover={{ scale: 1.02 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
            >
              <Link
                href="/#how-it-works"
                className="landing-pill-cta inline-flex items-center border border-border bg-white/70 px-7 py-3 text-sm font-semibold text-text-primary hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {heroData.secondaryCta}
              </Link>
            </motion.div>
          </motion.div>

          <motion.p className="mt-8 text-sm text-text-tertiary" variants={item}>
            PDF / DOCX in · source-linked DOCX response sheet out
          </motion.p>
        </motion.div>
      </motion.div>
    </section>
  );
}
