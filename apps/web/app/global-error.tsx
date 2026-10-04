"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "Inter, system-ui, sans-serif", background: "#f7f7f5", color: "#001742" }}>
        <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 32 }}>
          <section style={{ maxWidth: 520, background: "#fff", border: "1px solid #e8e8e5", borderRadius: 18, padding: 32 }}>
            <div style={{ width: 44, height: 44, marginBottom: 20 }}>
              <img src="/tce-mark.svg" alt="" width="44" height="44" />
            </div>
            <p style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.12em", color: "#4e5971" }}>Tender Compliance Engine</p>
            <h1 style={{ fontSize: 28, margin: "8px 0 10px" }}>The application could not recover.</h1>
            <p style={{ lineHeight: 1.6, color: "#4e5971" }}>Retry the application. Your uploaded source documents and persisted review state are not changed by this screen.</p>
            <button
              type="button"
              onClick={reset}
              style={{ marginTop: 18, border: 0, borderRadius: 8, background: "#1a5be7", color: "#fff", padding: "10px 16px", fontWeight: 700, cursor: "pointer" }}
            >
              Retry application
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
