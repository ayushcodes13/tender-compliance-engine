"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <head>
        {/* This screen renders its own <html>, outside the app layout, so it
            cannot rely on globals.css for @font-face. The font is self-hosted
            and the stack degrades to system-ui if the file cannot be fetched.
            It must not link out to Google: this app runs on customers' own
            infrastructure. */}
        <style>{`
          @font-face {
            font-family: "Plus Jakarta Sans";
            font-style: normal;
            font-weight: 300 800;
            font-display: swap;
            src: url("/fonts/plus-jakarta-sans-latin.woff2") format("woff2");
          }
        `}</style>
      </head>
      <body
        style={{
          margin: 0,
          fontFamily:
            '"Plus Jakarta Sans", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          background: "#f4f6f8",
          color: "#172033",
        }}
      >
        <main
          style={{
            minHeight: "100vh",
            display: "grid",
            placeItems: "center",
            padding: 32,
          }}
        >
          <section
            style={{
              maxWidth: 520,
              width: "100%",
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: 14,
              padding: 32,
              color: "#0f172a",
            }}
          >
            <div style={{ width: 44, height: 44, marginBottom: 20 }}>
              <img src="/tce-mark.svg" alt="" width="44" height="44" />
            </div>
            <p
              style={{
                fontSize: 11,
                textTransform: "uppercase",
                letterSpacing: "0.12em",
                color: "#94a3b8",
                margin: 0,
              }}
            >
              Tender Compliance Engine
            </p>
            <h1
              style={{
                margin: "8px 0 10px",
                fontSize: 24,
                fontWeight: 500,
                color: "#0f172a",
              }}
            >
              The application could not recover.
            </h1>
            <p
              style={{
                lineHeight: 1.6,
                color: "#64748a",
                fontSize: 14,
                margin: 0,
              }}
            >
              Retry the application. Your uploaded source documents and
              persisted review state are not changed by this screen.
            </p>
            <button
              type="button"
              onClick={reset}
              style={{
                marginTop: 16,
                border: 0,
                borderRadius: 10,
                background: "#2457d6",
                color: "#fff",
                padding: "10px 18px",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                transition: "background-color 0.2s ease",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget.style as any).background = "#1e49b8";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget.style as any).background = "#2457d6";
              }}
            >
              Retry application
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
