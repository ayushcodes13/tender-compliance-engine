type ScrollEventSource = Pick<EventTarget, "addEventListener" | "removeEventListener">;

/** Keep scroll-driven page selection quiet until a programmatic scroll settles. */
export function guardPageSyncUntilScrollSettles(
  target: ScrollEventSource,
  onSettled: () => void,
  options: { idleMs?: number; fallbackMs?: number } = {},
): () => void {
  const idleMs = options.idleMs ?? 180;
  const fallbackMs = options.fallbackMs ?? 5000;
  let active = true;
  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  let fallbackTimer: ReturnType<typeof setTimeout> | undefined;

  const cleanup = () => {
    target.removeEventListener("scroll", handleScroll);
    target.removeEventListener("scrollend", settle);
    if (idleTimer) clearTimeout(idleTimer);
    if (fallbackTimer) clearTimeout(fallbackTimer);
  };

  const settle = () => {
    if (!active) return;
    active = false;
    cleanup();
    onSettled();
  };

  const handleScroll = () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(settle, idleMs);
  };

  target.addEventListener("scroll", handleScroll, { passive: true });
  target.addEventListener("scrollend", settle);
  fallbackTimer = setTimeout(settle, fallbackMs);

  return () => {
    if (!active) return;
    active = false;
    cleanup();
  };
}
