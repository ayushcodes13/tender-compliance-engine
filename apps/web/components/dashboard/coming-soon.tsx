import { Clock } from "lucide-react";

export function ComingSoon({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center rounded-xl border border-border bg-surface p-12 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-accent/10 text-accent">
        <Clock size={22} aria-hidden="true" />
      </div>
      <h2 className="font-display text-2xl font-bold text-text-primary">
        {title}
      </h2>
      <p className="mt-3 max-w-md text-sm text-text-secondary">
        {description}
      </p>
      <p className="mt-6 text-xs text-text-tertiary">
        Not built yet. This page is a placeholder for a section that does not
        exist in this release.
      </p>
    </div>
  );
}