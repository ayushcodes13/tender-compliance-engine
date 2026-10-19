"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, minHeight: "100vh", display: "grid", placeItems: "center", background: "#f5f7fa", color: "#202b3c", fontFamily: "system-ui, sans-serif" }}>
        <main style={{ maxWidth: 420, padding: 32 }}>
          <h1>Something went wrong</h1>
          <p>Please try loading the tender again.</p>
          <button onClick={reset}>Try again</button>
        </main>
      </body>
    </html>
  );
}
