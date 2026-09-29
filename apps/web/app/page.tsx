const principles = [
  "Trace every requirement to source evidence",
  "Flag uncertainty instead of inventing certainty",
  "Keep numerical reasoning deterministic",
  "Human review before submission",
];

export default function Home() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Tender Compliance Engine</p>
        <h1>Technical tender requirements, extracted with provenance.</h1>
        <p className="lede">
          Phase 1 turns tender documents into reviewable, source-linked requirements and a clean
          compliance matrix. No invented specifications. No fake compliance decisions.
        </p>
      </section>

      <section className="card">
        <div>
          <span className="label">Current milestone</span>
          <strong>Repository foundation</strong>
        </div>
        <div>
          <span className="label">Next</span>
          <strong>Project creation + persistence</strong>
        </div>
      </section>

      <section className="principles">
        {principles.map((principle) => (
          <div className="principle" key={principle}>
            {principle}
          </div>
        ))}
      </section>
    </main>
  );
}
