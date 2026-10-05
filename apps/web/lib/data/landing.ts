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
  Zap,
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
  headline: "Source-linked compliance sheets for technical tenders.",
  subhead:
    "Upload a tender and your OEM evidence. Every requirement stays anchored to the page and clause it came from, so reviews and exports can be audited end to end.",
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
    title: "Tender document processing",
    description:
      "PDF and DOCX parsing with built-in OCR. Every extracted requirement stays linked to its exact page, clause, and source text — never fabricated.",
  },
  {
    icon: Search,
    title: "Requirement extraction & review",
    description:
      "Deterministic parsing pulls technical constraints, thresholds, units, tolerances, and ranges. A human-review layer flags OCR warnings and uncertainty.",
  },
  {
    icon: Shield,
    title: "Source-preserved compliance matrix",
    description:
      "A citation-backed matrix that can never hide an unresolved row. XLSX, DOCX, and PDF exports carry full source/version metadata.",
  },
  {
    icon: Zap,
    title: "Evidence-backed decisions",
    description:
      "Attach OEM datasheets, brochures, test reports, and quotations. A deterministic unit-normalisation engine compares values with auditable traceability.",
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
    title: "Review the requirements",
    description:
      "Confirm, correct, split, or merge each requirement. OCR warnings and ambiguous terms are flagged for you, not resolved by guesswork.",
    icon: Gavel,
  },
  {
    number: 3,
    title: "Upload OEM documents",
    description:
      "Attach datasheets, test reports, quotations, and existing compliance sheets as versioned evidence.",
    icon: FileText,
  },
  {
    number: 4,
    title: "Review evidence and decisions",
    description:
      "Accept or reject proposed evidence. Each comparison runs on tested code and shows the reasoning behind the result.",
    icon: Search,
  },
  {
    number: 5,
    title: "Export the compliance sheet",
    description:
      "Produce XLSX, DOCX, or PDF with full source and version metadata. Unresolved rows stay visible.",
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
    title: "Missing evidence is not non-compliance",
    description:
      "No attached evidence is recorded as unresolved, not as a failure. A gap in the pack never becomes an invented compliance verdict.",
  },
  {
    icon: BarChart3,
    title: "Deterministic comparison",
    description:
      "Thresholds, units, tolerances, and ranges are compared by tested code that shows its working, not by a language model judging numbers.",
  },
  {
    icon: Gavel,
    title: "Human review is a real step",
    description:
      "OCR warnings, ambiguous terms, and conflicts wait for an explicit decision. Unresolved items are surfaced in the sheet rather than quietly closed.",
  },
  {
    icon: FileText,
    title: "Immutable source versions",
    description:
      "Re-uploading a document creates a new version. Earlier evidence and the citations pointing at it stay intact.",
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
      "It turns a tender document into a source-linked compliance sheet. Requirements are extracted with the page and clause they came from, a reviewer confirms or corrects them, OEM evidence is attached, and each requirement is compared against that evidence with tested code.",
  },
  {
    question: "Do I need technical experience to use it?",
    answer:
      "No. The workflow is built for procurement and compliance reviewers. Where a result needs judgement — an OCR warning, an ambiguous term, a conflict — the system asks a human rather than guessing.",
  },
  {
    question: "How does it avoid inventing a compliance answer?",
    answer:
      "Every requirement keeps a link to its document version, page, and clause. Numeric thresholds, units, tolerances, and ranges are compared by deterministic code, not by a model. When evidence is missing, the sheet says so; missing evidence is never recorded as non-compliance.",
  },
  {
    question: "What files can I upload?",
    answer:
      "Tender documents and OEM documents are both accepted as PDF or DOCX. Scanned pages are handled with OCR, and any low-confidence recognition is flagged for review instead of being silently corrected.",
  },
  {
    question: "What can I export?",
    answer:
      "The compliance sheet exports to XLSX, DOCX, or PDF, carrying the source document and version metadata for every row. Unresolved rows stay visible in the export.",
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
