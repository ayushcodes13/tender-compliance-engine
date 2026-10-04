/**
 * Typed data objects for the Flowsuite-style landing page.
 *
 * All copy lives here so it can be swapped without touching components.
 */

import type { ComponentType } from "react";
import {
  BarChart3,
  FileText,
  Gavel,
  Link,
  Mic,
  Plus,
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
  { label: "Features", href: "/#features" },
  { label: "How it works", href: "/#how-it-works" },
  { label: "Pricing", href: "/#pricing" },
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
  eyebrow: "Enterprise-Grade Tender Compliance",
  headline: "From Tender Documents to a Source-Linked Compliance Sheet — Verified, Not Inferred.",
  subhead:
    "Upload your tender PDFs, extract every technical requirement with precise source anchors, review and normalise, then attach OEM evidence and export a submission that auditors can trace end to end.",
  primaryCta: "Get started free",
  secondaryCta: "Watch a 2-min demo",
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
    title: "Upload tender",
    description:
      "Upload a PDF or DOCX. Parsing and OCR keep every requirement tied to its source.",
    icon: FileText,
  },
  {
    number: 2,
    title: "Extract requirements",
    description:
      "Deterministic parsing extracts technical requirements with source anchors and confidence flags.",
    icon: Search,
  },
  {
    number: 3,
    title: "Review & normalise",
    description:
      "Review source-linked decisions, split, merge, categorise, and resolve OCR warnings.",
    icon: Gavel,
  },
  {
    number: 4,
    title: "Export compliance sheet",
    description:
      "Produce XLSX, DOCX, or PDF with full source/version metadata — unresolved rows stay visible.",
    icon: BarChart3,
  },
];

/* ------------------------------------------------------------------ */
/* Pricing                                                            */
/* ------------------------------------------------------------------ */

export interface PricingPlan {
  name: string;
  description: string;
  price: string;
  period: string;
  features: string[];
  cta: string;
  popular?: boolean;
}

export const pricingPlans: PricingPlan[] = [
  {
    name: "Starter",
    description:
      "Perfect for small teams and individual compliance analysts.",
    price: "$29",
    period: "/month",
    features: [
      "Up to 500 requirements per month",
      "5 GB document storage",
      "Standard OCR & extraction",
      "Basic compliance matrix",
      "XLSX & PDF export",
    ],
    cta: "Start free trial",
  },
  {
    name: "Professional",
    description:
      "Everything you need to manage tenders at scale.",
    price: "$99",
    period: "/month",
    features: [
      "Unlimited requirements",
      "50 GB document storage",
      "Advanced OCR & extraction",
      "Full compliance matrix",
      "XLSX, DOCX & PDF export",
      "Evidence-backed assessment",
      "Priority support",
    ],
    cta: "Start free trial",
    popular: true,
  },
  {
    name: "Enterprise",
    description:
      "Self-hosted or private-cloud, with dedicated support.",
    price: "Contact us",
    period: "",
    features: [
      "Unlimited everything",
      "Custom on-prem deployment",
      "SLAs and dedicated support",
      "API access",
      "Custom integrations",
    ],
    cta: "Contact sales",
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
    icon: Search,
    title: "Zero fabrication guarantee",
    description:
      "Every requirement is source-linked. The system never invents a clause, citation, or compliance status.",
  },
  {
    icon: Shield,
    title: "Audit-ready from day one",
    description:
      "Trace every decision back to its exact source document version, page, and offset.",
  },
  {
    icon: FileText,
    title: "Multi-format export",
    description:
      "Generate XLSX, DOCX, or PDF compliance sheets with full version metadata and evidence links.",
  },
  {
    icon: Zap,
    title: "Human-in-the-loop review",
    description:
      "OCR warnings, uncertainty, and unresolved conflicts surface for explicit review — never silent.",
  },
  {
    icon: BarChart3,
    title: "Deterministic comparisons",
    description:
      "Units, thresholds, tolerances, and ranges are compared with tested logic, not LLM judgement.",
  },
  {
    icon: Upload,
    title: "Separate tender & vendor docs",
    description:
      "Upload tenders and OEM evidence independently. Each source is versioned immutably and isolated by tenant.",
  },
];

/* ------------------------------------------------------------------ */
/* Testimonials                                                       */
/* ------------------------------------------------------------------ */

export interface Testimonial {
  quote: string;
  name: string;
  role: string;
  image?: string;
}

export const testimonials: Testimonial[] = [
  {
    quote:
      "Tender Compliance Engine cut our review cycle from days to hours. The source linking alone saved us from a costly compliance error.",
    name: "Sarah Chen",
    role: "Head of Procurement, Veridian Dynamics",
  },
  {
    quote:
      "Finally a tool that doesn't hide unresolved rows. Our legal team can audit every decision back to the original PDF page.",
    name: "Marcus Rivera",
    role: "Legal Counsel, Apex Tenders",
  },
  {
    quote:
      "The deterministic unit comparison caught three cases where vendor datasheets used different metrics. No AI hallucinations, just correct math.",
    name: "Dr. Elena Volkov",
    role: "Chief Engineer, NordLink Industries",
  },
];

/* ------------------------------------------------------------------ */
/* Integrations                                                       */
/* ------------------------------------------------------------------ */

export interface Integration {
  name: string;
}

export const integrations: Integration[] = [
  { name: "SAP" },
  { name: "Salesforce" },
  { name: "SharePoint" },
  { name: "Google Workspace" },
  { name: "Notion" },
  { name: "Jira" },
  { name: "ServiceNow" },
  { name: "Monday.com" },
];

/* ------------------------------------------------------------------ */
/* Social proof                                                       */
/* ------------------------------------------------------------------ */

export interface SocialProofData {
  stat: string;
  label: string;
  companies: string[];
}

export const socialProofData: SocialProofData = {
  stat: "10,000+",
  label: "tender requirements reviewed",
  companies: [
    "Veridian",
    "Apex Tenders",
    "NordLink",
    "Summit Procurement",
    "Cobalt Contracts",
  ],
};

/* ------------------------------------------------------------------ */
/* FAQ                                                                */
/* ------------------------------------------------------------------ */

export interface FaqItem {
  question: string;
  answer: string;
}

export const faqs: FaqItem[] = [
  {
    question: "What is Tender Compliance Engine and who is it for?",
    answer:
      "It is a tool for procurement and compliance teams who need to turn tender documents into source-linked, human-reviewable compliance sheets. Whether you are a prime contractor, an OEM, or a procurement consultant, the engine keeps every decision traceable to its original source.",
  },
  {
    question: "Do I need technical experience to use it?",
    answer:
      "No. The web UI is designed for non-technical reviewers. Power users can extend the deterministic parsers and unit-comparison engine via configuration.",
  },
  {
    question: "Is my data secure?",
    answer:
      "Documents are treated as untrusted input. Uploads are validated, malware-scanned in production, and stored with immutable versioning. You can run the engine self-hosted on your own infrastructure.",
  },
  {
    question: "Can I export to XLSX, DOCX, and PDF?",
    answer:
      "Yes. Every export carries full source document and version metadata. Unresolved rows are always visible — never hidden.",
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
      { label: "Features", href: "/features" },
      { label: "Pricing", href: "/pricing" },
      { label: "Contact", href: "/contact" },
    ],
  },
  {
    title: "Resources",
    links: [
      { label: "Documentation", href: "/docs" },
      { label: "Blog", href: "/blog" },
      { label: "Security", href: "/security" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy Policy", href: "/privacy-policy" },
      { label: "Terms & Conditions", href: "/terms-and-conditions" },
      { label: "Cookie Policy", href: "/cookie-policy" },
    ],
  },
];

export const footerCopyright =
  "© 2025 Tender Compliance Engine. All rights reserved.";
