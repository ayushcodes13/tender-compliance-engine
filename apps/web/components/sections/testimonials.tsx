"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Star } from "lucide-react";

import { testimonials } from "@/lib/data/landing";

export function TestimonialsSection() {
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
            Trusted by Teams Worldwide
          </h2>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-text-secondary">
            Join procurement and compliance teams who rely on source-linked
            decisions.
          </p>
        </motion.div>

        <motion.div
          className="grid gap-6 md:grid-cols-2 lg:grid-cols-3"
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, amount: 0.1 }}
          variants={{
            animate: {
              transition: {
                staggerChildren: 0.15,
                delayChildren: 0.1,
              },
            },
          }}
        >
          {testimonials.map((t, index) => (
            <motion.div
              key={t.name}
              className={cn(
                "flex flex-col gap-4 rounded-xl border border-border bg-surface p-7",
                "transition-all duration-300 hover:border-accent/50",
              )}
              variants={{
                initial: { opacity: 0, y: 20 },
                animate: { opacity: 1, y: 0 },
              }}
              transition={{
                duration: 0.6,
                delay: index * 0.15,
                ease: [0.16, 1, 0.3, 1] as const,
              }}
              whileHover={{ y: -4 }}
            >
              <div className="flex gap-0.5 text-accent">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star key={i} className="h-4 w-4 fill-current" />
                ))}
              </div>
              <p className="text-sm italic text-text-secondary">
                "{t.quote}"
              </p>
              <div className="mt-auto flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
                  <span className="text-sm font-bold">
                    {t.name
                      .split(" ")
                      .map((n) => n[0])
                      .join("")}
                  </span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-text-primary">
                    {t.name}
                  </p>
                  <p className="text-xs text-text-tertiary">{t.role}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
