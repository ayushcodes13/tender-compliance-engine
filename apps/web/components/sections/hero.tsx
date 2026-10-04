"use client";

import Link from "next/link";
import { motion } from "framer-motion";

import { heroData } from "@/lib/data/landing";

const container = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: {
      duration: 0.8,
      ease: [0.16, 1, 0.3, 1] as const,
      staggerChildren: 0.1,
      delayChildren: 0.1,
    },
  },
};

const item = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
};

export function HeroSection() {
  return (
    <section className="relative flex min-h-[90vh] w-full items-center justify-center overflow-hidden">
      {/* Gradient orbs */}
      <div
        className="absolute inset-0 pointer-events-none"
        aria-hidden="true"
      >
        <motion.div
          className="absolute -top-1/3 left-1/2 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-accent/5"
          animate={{
            scale: [1, 1.05, 1],
            opacity: [0.3, 0.4, 0.3],
          }}
          transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
        />
        <div className="absolute -bottom-1/3 left-1/4 h-[400px] w-[400px] rounded-full bg-purple-500/5" />
      </div>

      <motion.div
        className="relative z-10 container mx-auto flex flex-col items-center px-6 text-center md:px-8"
        variants={container}
        initial="initial"
        animate="animate"
      >
        <motion.p
          className="text-sm font-medium text-accent"
          variants={item}
        >
          {heroData.eyebrow}
        </motion.p>

        <motion.h1
          className="mt-6 max-w-4xl font-display text-4xl font-bold tracking-tight text-text-primary sm:text-5xl lg:text-6xl"
          style={{ lineHeight: 1.05 }}
          variants={item}
        >
          {heroData.headline}
        </motion.h1>

        <motion.p
          className="mt-6 max-w-2xl text-lg text-text-secondary"
          style={{ lineHeight: 1.6 }}
          variants={item}
        >
          {heroData.subhead}
        </motion.p>

        <motion.div
          className="mt-10 flex flex-col gap-4 sm:flex-row"
          variants={item}
        >
          <Link href="/sign-up">
            <motion.button
              className="rounded-full bg-accent px-8 py-3 text-sm font-semibold text-background shadow-lg shadow-accent/20 hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              whileHover={{ scale: 1.03 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
            >
              {heroData.primaryCta}
            </motion.button>
          </Link>
          <Link href="/features">
            <motion.button
              className="rounded-full border border-border bg-transparent px-8 py-3 text-sm font-semibold text-text-primary hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              whileHover={{ scale: 1.03 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
            >
              {heroData.secondaryCta}
            </motion.button>
          </Link>
        </motion.div>
      </motion.div>
    </section>
  );
}
