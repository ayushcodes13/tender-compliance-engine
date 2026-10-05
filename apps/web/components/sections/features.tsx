"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

import { features } from "@/lib/data/landing";

const container = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: {
      duration: 0.6,
      ease: [0.16, 1, 0.3, 1] as const,
      staggerChildren: 0.1,
      delayChildren: 0.05,
    },
  },
};

const cardVariants = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
};

export function FeaturesSection() {
  return (
    <section className="landing-section-premium w-full bg-surface py-20 md:py-28">
      <div className="container mx-auto px-6 md:px-8">
        <motion.div
          className="mb-12 text-center"
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
        >
          <h2 className="font-display text-3xl text-text-primary sm:text-4xl">
            Source-linked extraction with review
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-text-secondary">
            Every requirement is extracted with a precise source anchor,
            reviewed by your team, then exported as a citation-backed matrix.
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
                  "premium-feature-card flex flex-col gap-4",
                  "hover:border-accent",
                )}
                variants={cardVariants}
                transition={{
                  duration: 0.5,
                  delay: index * 0.08,
                  ease: [0.16, 1, 0.3, 1] as const,
                }}
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent-soft text-accent">
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
