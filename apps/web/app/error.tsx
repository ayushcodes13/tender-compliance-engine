"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mvp-fatal-error">
      <h1>Tender Review could not load.</h1>
      <p>Retry the page. The app does not store the current tender.</p>
      <button type="button" onClick={reset}>Try again</button>
    </main>
  );
}
