import { type Variants } from "framer-motion";

/**
 * Soft ease-out cubic-bezier curve [0.16, 1, 0.3, 1].
 * `as const` ensures TypeScript infers a readonly 4-tuple (BezierDefinition)
 * rather than the wider `number[]`, which Framer Motion's `Variants`
 * transition type rejects.
 */
export const easeOut = [0.16, 1, 0.3, 1] as const;

/** Standard section-enter: fade up over 700 ms. */
export const fadeUp: Variants = {
  initial: { opacity: 0, y: 30 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.7, ease: easeOut },
  },
};

/** Staggered children container. */
export const staggerContainer: Variants = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: {
      staggerChildren: 0.12,
      delayChildren: 0.1,
    },
  },
};
