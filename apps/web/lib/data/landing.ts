/**
 * Typed data objects for the landing page.
 *
 * Copy lives here so it can be swapped without touching components.
 * Every string below is a factual statement about what this code does,
 * traceable to the backend or the UI. There are no customers, testimonials,
 * adoption numbers, integrations, pricing tiers, trial lengths, or SLA
 * claims, because none of those have been established.
 *
 * When you add a claim here, it must be something the product demonstrably
 * does today. "A pilot customer reduced review time" needs a named pilot
 * and a measured number; without them, leave it out.
 */

import type { ComponentType } from "react";
import {
  BarChart3,
  FileText,
  Gavel,
  Search,
  Shield,
  Upload,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/* Navigation                                                         */
/* ------------------------------------------------------------------ */

export interface NavItem {
  label: string;
  href: string;
}

export const navItems: NavItem[] = [
  { label: "What it does", href: "/#features" },
  { label: "How it works", href: "/#how-it-works" },
  { label: "FAQ", href: "/#faq" },
  { label: "Contact", href: "/contact" },
];

/* ------------------------------------------------------------------ */
/* Hero                                                               */
/* ------------------------------------------------------------------ */

export interface HeroData {
  eyebrow: string;
  headline: string;
  subhead: string;
  primaryCta: string;
  secondaryCta: string;
}

export const heroData: HeroData = {
  eyebrow: "For procurement, technical sales, and bid teams",
  headline: "Technical tender specifications, ready for OEM response.",
  subhead:
    "Upload a tender to extract and organize only the technical specifications it already contains. Review each item against its cited source, then export a response sheet with blank fields for the OEM.",
  primaryCta: "Book a pilot",
  secondaryCta: "See how it works",
};

/* ------------------------------------------------------------------ */
/* Features                                                           */
/* ------------------------------------------------------------------ */

export interface Feature {
  icon: ComponentType<{ className?: string }>;
  title: string;
  description: string;
}

export const features: Feature[] = [
  {
    icon: Upload,
    title: "Tender parsing and OCR",
    description:
      "Process PDF and DOCX tenders. Scanned text and uncertain symbols stay flagged for review instead of being silently corrected.",
  },
  {
    icon: Search,
    title: "Technical specifications from the tender",
    description:
      "Keep the tender's wording, values, units, tolerances, conditions, numbering, and nested rows together for the OEM to answer.",
  },
  {
    icon: Shield,
    title: "Review beside the cited page",
    description:
      "Open a row's tender page, check the exact excerpt, and resolve uncertain extraction before exporting.",
  },
  {
    icon: FileText,
    title: "Blank OEM response sheet",
    description:
      "Export the tender's technical specifications in a clean structure with response fields left for the supplier to complete.",
  },
];

/* ------------------------------------------------------------------ */
/* How it works (buyer flow)                                          */
/* ------------------------------------------------------------------ */

export interface WorkflowStep {
  number: number;
  title: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
}

export const workflowSteps: WorkflowStep[] = [
  {
    number: 1,
    title: "Upload the tender",
    description:
      "Upload a PDF or DOCX. Parsing and OCR keep every requirement tied to the page and clause it came from.",
    icon: Upload,
  },
  {
    number: 2,
    title: "Organize the technical specifications",
    description:
      "Keep numbered items and nested rows together. Correct extraction or structure without changing the tender's technical meaning.",
    icon: Gavel,
  },
  {
    number: 3,
    title: "Verify each source",
    description:
      "Open the cited tender page to confirm wording, values, units, and source location. Uncertain items remain visible for review.",
    icon: Search,
  },
  {
    number: 4,
    title: "Export the OEM response sheet",
    description:
      "Download a source-linked sheet containing the tender's technical specifications and blank supplier response fields.",
    icon: BarChart3,
  },
];

/* ------------------------------------------------------------------ */
/* Benefits                                                           */
/* ------------------------------------------------------------------ */

export interface Benefit {
  title: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
}

export const benefits: Benefit[] = [
  {
    icon: Shield,
    title: "Source-linked",
    description:
      "Every requirement carries its document version, page, and clause. The system does not invent a citation, and a location it does not know stays unknown rather than guessed.",
  },
  {
    icon: Search,
    title: "No invented specifications",
    description:
      "The sheet is derived from the tender. It does not add recommendations, assumptions, or OEM compliance decisions.",
  },
  {
    icon: BarChart3,
    title: "Technical wording stays traceable",
    description:
      "Each extracted item links back to its tender page and source excerpt so a reviewer can check it before export.",
  },
  {
    icon: Gavel,
    title: "Human review is a real step",
    description:
      "OCR warnings, ambiguous terms, and conflicts wait for an explicit decision. Unresolved items are surfaced in the sheet rather than quietly closed.",
  },
  {
    icon: FileText,
    title: "Numbered and nested rows",
    description:
      "Keep a main item and its a), b), c) sub-items visually grouped so the OEM can respond row by row.",
  },
  {
    icon: Upload,
    title: "Untrusted uploads handled as such",
    description:
      "Files are validated and malware-scanned before processing, and document content is never treated as instructions to the application.",
  },
];

/* ------------------------------------------------------------------ */
/* FAQ                                                                */
/* ------------------------------------------------------------------ */

export interface FaqItem {
  question: string;
  answer: string;
}

export const faqs: FaqItem[] = [
  {
    question: "What does it do?",
    answer:
      "It extracts and organizes the technical specifications already present in a tender, keeps each item linked to its source page, and exports a response sheet with blank fields for the OEM. It does not determine whether an OEM complies.",
  },
  {
    question: "Do I need technical experience to use it?",
    answer:
      "No. The workflow is built for procurement and compliance reviewers. Where a result needs judgement — an OCR warning, an ambiguous term, a conflict — the system asks a human rather than guessing.",
  },
  {
    question: "Does it add or interpret technical requirements?",
    answer:
      "No. The response sheet contains tender-derived technical specifications only. It preserves source wording and flags uncertain extraction for human review rather than guessing or adding a compliance decision.",
  },
  {
    question: "What files can I upload?",
    answer:
      "Upload a tender as PDF or DOCX. Scanned pages are handled with OCR, and uncertain recognition is flagged for review instead of being silently corrected.",
  },
  {
    question: "What can I export?",
    answer:
      "Export a DOCX response sheet with the tender's technical specifications and blank OEM response fields. Source links and validation details remain available in the application for review.",
  },
  {
    question: "Where does my data go?",
    answer:
      "The engine runs in your own deployment. Uploads are validated and malware-scanned before processing, and stored with immutable versioning. Document text used for requirement extraction is sent to the model provider you configure, and that provider must be covered by your own data-processing agreement.",
  },
  {
    question: "How do I get access?",
    answer:
      "It is currently offered as a private pilot in a single-workspace deployment. Contact us to talk through your tender process and documents.",
  },
];

/* ------------------------------------------------------------------ */
/* Footer                                                             */
/* ------------------------------------------------------------------ */

export interface FooterColumn {
  title: string;
  links: { label: string; href: string }[];
}

export const footerColumns: FooterColumn[] = [
  {
    title: "Product",
    links: [
      { label: "What it does", href: "/#features" },
      { label: "How it works", href: "/#how-it-works" },
      { label: "Contact", href: "/contact" },
    ],
  },
  {
    title: "Source",
    links: [
      { label: "FAQ", href: "/#faq" },
      {
        label: "GitHub",
        href: "https://github.com/ayushcodes13/tender-compliance-engine",
      },
    ],
  },
];

export const footerCopyright =
  "© Tender Compliance Engine. All rights reserved.";
