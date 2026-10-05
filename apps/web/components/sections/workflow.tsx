"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

import { workflowSteps } from "@/lib/data/landing";

const item = {
  initial: { opacity: 0, x: -20 },
  animate: { opacity: 1, x: 0 },
};

export function WorkflowSection() {
  return (
    <section className="w-full border-y border-border bg-background py-20 md:py-28">
      <div className="container mx-auto px-6 md:px-8">
        <motion.div
          className="mb-12 text-center"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] as const }}
        >
          <h2 className="font-display text-3xl font-bold tracking-tight text-text-primary sm:text-4xl">
            From Tender to Compliance Sheet
          </h2>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-text-secondary">
            Five steps. Each decision stays tied to its source.
          </p>
        </motion.div>

        <motion.div
          className="overflow-hidden rounded-xl border border-border bg-surface"
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, amount: 0.2 }}
          variants={{
            animate: {
              transition: {
                staggerChildren: 0.12,
                delayChildren: 0.1,
              },
            },
          }}
        >
          {workflowSteps.map((step) => {
            const Icon = step.icon;
            return (
              <motion.div
                key={step.number}
                className={cn(
                  "flex items-start gap-5 border-b border-border p-6 last:border-b-0",
                  "transition-colors duration-200 hover:bg-surface-elevated",
                )}
                variants={{
                  initial: { opacity: 0, x: -20 },
                  animate: { opacity: 1, x: 0 },
                }}
                transition={{
                  duration: 0.6,
                  delay: step.number * 0.1,
                  ease: [0.16, 1, 0.3, 1] as const,
                }}
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent-soft text-sm font-bold text-accent">
                  {step.number}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-accent" />
                    <h3 className="font-semibold text-text-primary">
                      {step.title}
                    </h3>
                  </div>
                  <p className="mt-1 text-sm text-text-secondary">
                    {step.description}
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
