import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, FileSearch, ScanSearch, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/mvp/app-shell";

export const metadata = { title: "How it works" };

export default function MethodPage() {
  return <AppShell active="method">
    <main className="method-page">
      <Link className="saas-back-link" href="/dashboard"><ArrowLeft size={15}/>Back to overview</Link>
      <header className="method-intro"><div className="saas-eyebrow">HOW THE REVIEW WORKS</div><h1>A traceable path from PDF to response draft.</h1><p>The app keeps the source document beside each extracted requirement so a person can verify the wording before it moves into a response sheet.</p></header>
      <section className="method-flow">
        <article><div className="method-step"><span>01</span><FileSearch size={19}/></div><h2>Read the PDF</h2><p>The browser sends a text-based PDF to a small server action. PDF.js reads selectable text and page positions. Scanned files need OCR, which this MVP does not include.</p><div className="method-detail">Input: up to 4 MB · 120 pages · selectable text</div></article>
        <article><div className="method-step"><span>02</span><ScanSearch size={19}/></div><h2>Match quotes to page text</h2><p>The model suggests exact page-local requirement quotes. The server searches each quote in extracted text and builds a highlight from the positions of matching text items.</p><div className="method-detail">Only matched quotes receive an exact highlight</div></article>
        <article><div className="method-step"><span>03</span><Check size={19}/></div><h2>Review and export</h2><p>You inspect the cited page, mark each item checked, then download a DOCX draft with blank response fields. The draft is not a completeness guarantee.</p><div className="method-detail">Reviewer confirmation stays in this session</div></article>
      </section>
      <aside className="method-callout"><ShieldCheck size={18}/><p><strong>Keep the source in control.</strong> Every row should be checked against the tender. This demo does not save upload history or claim that extraction is exhaustive.</p></aside>
      <Link className="saas-button" href="/new">Start a review <ArrowRight size={16}/></Link>
    </main>
  </AppShell>;
}
