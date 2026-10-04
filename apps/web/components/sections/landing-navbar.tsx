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
      className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/80 backdrop-blur-sm"
      initial="initial"
      animate="animate"
      variants={navVariants}
    >
      <div className="container mx-auto flex h-16 items-center justify-between px-6 md:px-8">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10">
            <span className="text-lg">🛡️</span>
          </span>
          <span>Tender Compliance Engine</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-6">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm text-text-secondary hover:text-text-primary transition-colors"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        {/* Auth buttons */}
        <div className="flex items-center gap-3">
          <Link
            href="/sign-in"
            className="hidden text-sm font-medium text-text-secondary hover:text-text-primary md:inline-block"
          >
            Sign in
          </Link>
          <Link href="/sign-up">
            <motion.button
              className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-background hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              whileHover={{ scale: 1.03 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
            >
              Get started
            </motion.button>
          </Link>
        </div>
      </div>
    </motion.header>
  );
}
