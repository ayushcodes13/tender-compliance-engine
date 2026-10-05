"use client";

import Link from "next/link";
import { motion } from "framer-motion";

import { navItems } from "@/lib/data/landing";

const navVariants = {
  initial: { opacity: 0, y: -10 },
  animate: { opacity: 1, y: 0 },
};

export function LandingNavbar() {
  return (
    <motion.header
      className="sticky top-0 z-50 w-full border-b border-border bg-background"
      initial="initial"
      animate="animate"
      variants={navVariants}
    >
      <div className="container mx-auto flex h-16 items-center justify-between px-6 md:px-8">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <img
            src="/tce-mark.svg"
            alt=""
            width={34}
            height={34}
            className="h-8 w-8"
          />
          <span>Tender Compliance Engine</span>
        </Link>

        {/* Desktop nav */}
        <nav aria-label="Main" className="hidden md:flex items-center gap-6">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm text-text-secondary hover:text-accent transition-colors"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <Link
            href="/access"
            className="hidden text-sm font-medium text-text-secondary hover:text-text-primary md:inline-block"
          >
            Access
          </Link>
          <motion.div
              whileHover={{ scale: 1.03 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
            >
              <Link
                href="/contact"
                className="inline-flex items-center rounded-md bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                Book a pilot
              </Link>
            </motion.div>
        </div>
      </div>
    </motion.header>
  );
}
