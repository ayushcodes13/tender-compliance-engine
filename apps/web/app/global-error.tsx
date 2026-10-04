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
        <link
          href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600;700&family=Figtree:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        style={{
          margin: 0,
          fontFamily:
            '"Figtree", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          background: "#0a0a0a",
          color: "#e4e4e3",
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
                fontFamily: '"EB Garamond", Georgia, serif',
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
                background: "#ff6c4c",
                color: "#fff",
                padding: "10px 18px",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                transition: "background-color 0.2s ease",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget.style as any).background = "#e55a3e";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget.style as any).background = "#ff6c4c";
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
