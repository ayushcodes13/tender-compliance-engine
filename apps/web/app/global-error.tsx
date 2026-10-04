"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", background: "#ffffff", color: "#0f172a" }}>
        <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 32 }}>
          <section style={{ maxWidth: 520, background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 32 }}>
            <div style={{ width: 44, height: 44, marginBottom: 20 }}>
              <img src="/tce-mark.svg" alt="" width="44" height="44" />
            </div>
            <p style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.12em", color: "#64748a" }}>Tender Compliance Engine</p>
            <h1 style={{ fontSize: 24, margin: "8px 0 10px", fontWeight: 500 }}>The application could not recover.</h1>
            <p style={{ lineHeight: 1.6, color: "#64748a", fontSize: 14 }}>Retry the application. Your uploaded source documents and persisted review state are not changed by this screen.</p>
            <button
              type="button"
              onClick={reset}
              style={{ marginTop: 16, border: 0, borderRadius: 6, background: "#2563eb", color: "#fff", padding: "9px 16px", fontSize: 13, fontWeight: 500, cursor: "pointer" }}
            >
              Retry application
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
