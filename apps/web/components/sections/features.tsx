"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

import { features } from "@/lib/data/landing";

const container = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: {
      duration: 0.7,
      ease: [0.16, 1, 0.3, 1] as const,
      staggerChildren: 0.12,
      delayChildren: 0.1,
    },
  },
};

const cardVariants = {
  initial: { opacity: 0, y: 30, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1 },
};

export function FeaturesSection() {
  return (
    <section className="w-full py-20 md:py-28">
      <div className="container mx-auto px-6 md:px-8">
        <motion.div
          className="mb-14 text-center"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] as const }}
        >
          <h2 className="font-display text-3xl font-bold tracking-tight text-text-primary sm:text-4xl">
            Smarter Tools to Accelerate Your Growth
          </h2>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-text-secondary">
            Powerful capabilities designed to simplify workflows and ensure
            compliance without the spreadsheet hunt.
          </p>
        </motion.div>

        <motion.div
          className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4"
          variants={container}
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, amount: 0.2 }}
        >
          {features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <motion.div
                key={feature.title}
                className={cn(
                  "group flex flex-col gap-4 rounded-xl border border-border bg-surface p-7",
                  "transition-all duration-300 hover:border-accent/50 hover:bg-surface-elevated",
                )}
                variants={cardVariants}
                transition={{
                  duration: 0.6,
                  delay: index * 0.1,
                  ease: [0.16, 1, 0.3, 1] as const,
                }}
                whileHover={{ y: -4 }}
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10 text-accent">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="font-semibold text-text-primary">
                  {feature.title}
                </h3>
                <p className="text-sm text-text-secondary">
                  {feature.description}
                </p>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}
