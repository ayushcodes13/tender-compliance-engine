"use client";

import { motion } from "framer-motion";

import { integrations } from "@/lib/data/landing";

export function IntegrationsSection() {
  return (
    <section className="w-full py-16">
      <div className="container mx-auto px-6 md:px-8">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.5 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] as const }}
        >
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-text-tertiary">
            Integrations
          </h3>
          <p className="text-text-secondary">
            Works with the tools your team already uses.
          </p>

          <motion.div
            className="mt-8 flex flex-wrap items-center justify-center gap-x-8 gap-y-4 opacity-60"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 0.6 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            {integrations.map((int) => (
              <motion.span
                key={int.name}
                className="text-sm font-medium text-text-tertiary"
                whileHover={{ opacity: 1 }}
                transition={{ duration: 0.2 }}
              >
                {int.name}
              </motion.span>
            ))}
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
