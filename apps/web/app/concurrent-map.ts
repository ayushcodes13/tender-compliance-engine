/** Run independent work with a fixed number of workers, scheduling the next
 * item as soon as any worker finishes while preserving result order. */
export async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  mapItem: (item: T, index: number) => Promise<R>,
  onItemComplete?: (completed: number, total: number) => void,
): Promise<R[]> {
  if (!Number.isInteger(concurrency) || concurrency < 1) throw new Error("Concurrency must be a positive integer.");
  const results = new Array<R>(items.length);
  let nextIndex = 0;
  let completed = 0;
  const worker = async () => {
    while (true) {
      const index = nextIndex++;
      if (index >= items.length) return;
      results[index] = await mapItem(items[index], index);
      completed += 1;
      onItemComplete?.(completed, items.length);
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
  return results;
}
