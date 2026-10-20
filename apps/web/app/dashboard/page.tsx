import Link from "next/link";
import { ArrowRight, FileCheck2, FilePlus2, FileSearch, Quote, ScanSearch } from "lucide-react";
import { AppShell } from "@/components/mvp/app-shell";

export const metadata = { title: "Overview" };

export default function DashboardPage() {
  return <AppShell active="dashboard">
    <main className="dashboard-page">
      <section className="dashboard-welcome">
        <div><div className="saas-eyebrow">TENDER REVIEW · WORKSPACE</div><h1>Make every requirement easy to verify.</h1><p>Extract technical requirements, check the source on the page, then prepare a response sheet.</p></div>
        <Link className="saas-button" href="/new">Start a review <ArrowRight size={16}/></Link>
      </section>
      <section className="dashboard-metrics" aria-label="Workspace capabilities">
        <article><span className="metric-icon"><FileCheck2 size={18}/></span><div><strong>Source matched</strong><small>Quotes must be found on the cited page</small></div></article>
        <article><span className="metric-icon amber"><ScanSearch size={18}/></span><div><strong>Page highlights</strong><small>Bounding boxes connect quote to source</small></div></article>
        <article><span className="metric-icon green"><Quote size={18}/></span><div><strong>Human checked</strong><small>You review before exporting a response</small></div></article>
      </section>
      <section className="dashboard-content-grid">
        <article className="dashboard-card recent-card">
          <div className="saas-card-heading"><div><span className="saas-eyebrow">YOUR WORK</span><h2>Recent reviews</h2></div><span className="session-tag">This session</span></div>
          <div className="dashboard-empty"><span className="empty-icon"><FileSearch size={22}/></span><h3>No reviews yet</h3><p>Start with a text-based tender PDF. Your document stays in this browser session and is not added to a review history.</p><Link href="/new" className="saas-text-link">Upload a tender <ArrowRight size={15}/></Link></div>
        </article>
        <article className="dashboard-card getting-started">
          <span className="saas-eyebrow">QUICK START</span><h2>Three steps to a response sheet</h2>
          <ol><li><i>1</i><span><strong>Choose your tender</strong><small>Text-based PDF, up to 4 MB and 120 pages.</small></span></li><li><i>2</i><span><strong>Review source evidence</strong><small>Open each cited page and check the highlight.</small></span></li><li><i>3</i><span><strong>Export your draft</strong><small>Download a DOCX with blank response fields.</small></span></li></ol>
          <Link href="/method" className="saas-text-link">See how evidence is matched <ArrowRight size={15}/></Link>
        </article>
      </section>
      <footer className="saas-page-foot">AI-assisted review can miss requirements. Confirm all output against the original tender.</footer>
    </main>
  </AppShell>;
}
