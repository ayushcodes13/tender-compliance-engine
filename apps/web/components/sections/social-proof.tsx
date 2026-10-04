"use client";

import { motion } from "framer-motion";

import { socialProofData } from "@/lib/data/landing";

const marqueeVariants = {
  animate: {
    x: ["0%", "-100%"],
    transition: {
      x: {
        duration: 30,
        repeat: Infinity,
        ease: "linear" as const,
      },
    },
  },
};

export function SocialProofSection() {
  return (
    <section className="w-full border-t border-border/50 py-12">
      <div className="container mx-auto px-6 md:px-8">
        <div className="mb-8 text-center">
          <p className="text-sm text-text-tertiary">
            <span className="font-semibold text-accent">
              {socialProofData.stat}
            </span>{" "}
            {socialProofData.label}
          </p>
        </div>

        <motion.div
          className="flex items-center justify-center gap-8 flex-wrap md:justify-between"
          variants={marqueeVariants}
          animate="animate"
        >
          {socialProofData.companies.map((company) => (
            <motion.span
              key={company}
              className="text-sm font-medium text-text-tertiary opacity-70"
              whileHover={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
            >
              {company}
            </motion.span>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
