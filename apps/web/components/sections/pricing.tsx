"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

import { pricingPlans } from "@/lib/data/landing";

const item = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
};

export function PricingSection() {
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
            Flexible Pricing Plans
          </h2>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-text-secondary">
            Choose a plan that fits your needs. No hidden fees.
          </p>
        </motion.div>

        <motion.div
          className="grid gap-6 lg:grid-cols-3"
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
          {pricingPlans.map((plan, index) => (
            <motion.div
              key={plan.name}
              className={cn(
                "relative flex flex-col rounded-2xl border p-8",
                "bg-surface transition-all duration-300",
                plan.popular
                  ? "border-accent shadow-xl shadow-accent/10"
                  : "border-border hover:border-accent/50",
              )}
              variants={item}
              transition={{
                duration: 0.6,
                delay: index * 0.15,
                ease: [0.16, 1, 0.3, 1] as const,
              }}
              whileHover={{ y: -6 }}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-accent px-3 py-1 text-xs font-semibold text-background">
                  Most popular
                </div>
              )}

              <h3 className="text-xl font-semibold text-text-primary">
                {plan.name}
              </h3>
              <p className="mt-1 text-sm text-text-secondary">
                {plan.description}
              </p>

              <div className="my-6">
                <span className="text-4xl font-bold text-text-primary">
                  {plan.price}
                </span>
                {plan.period && (
                  <span className="text-text-tertiary">{plan.period}</span>
                )}
              </div>

              <ul className="mb-8 space-y-2 text-sm">
                {plan.features.map((feature) => (
                  <li
                    key={feature}
                    className="flex items-center gap-2 text-text-secondary"
                  >
                    <svg
                      className="h-4 w-4 text-accent"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              <Link
                href="/sign-up"
                className={cn(
                  "mt-auto rounded-full px-6 py-3 text-center text-sm font-semibold",
                  plan.popular
                    ? "bg-accent text-background hover:bg-accent-hover"
                    : "border border-border bg-surface-elevated text-text-primary hover:bg-border",
                )}
              >
                {plan.cta}
              </Link>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
