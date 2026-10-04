"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

import { benefits } from "@/lib/data/landing";

const item = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
};

export function BenefitsSection() {
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
            The Powerful Advantages Your Team Gets
          </h2>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-text-secondary">
            Built for procurement and compliance teams who need certainty, not
            approximations.
          </p>
        </motion.div>

        <motion.div
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, amount: 0.1 }}
          variants={{
            animate: {
              transition: {
                staggerChildren: 0.1,
                delayChildren: 0.1,
              },
            },
          }}
        >
          {benefits.map((benefit, index) => {
            const Icon = benefit.icon;
            return (
              <motion.div
                key={benefit.title}
                className={cn(
                  "flex items-start gap-4 rounded-xl border border-border bg-surface p-6",
                  "transition-all duration-300 hover:border-accent/50 hover:bg-surface-elevated",
                )}
                variants={item}
                transition={{
                  duration: 0.6,
                  delay: index * 0.1,
                  ease: [0.16, 1, 0.3, 1] as const,
                }}
                whileHover={{ y: -3 }}
              >
                <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10 text-accent">
                  <Icon className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="font-semibold text-text-primary">
                    {benefit.title}
                  </h3>
                  <p className="mt-1 text-sm text-text-secondary">
                    {benefit.description}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}
