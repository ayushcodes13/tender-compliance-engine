export async function mapInConcurrentWaves<T, R>(
  items: T[],
  concurrency: number,
  mapItem: (item: T, index: number) => Promise<R>,
  onWaveComplete?: (completed: number, total: number) => void,
): Promise<R[]> {
  if (!Number.isInteger(concurrency) || concurrency < 1) throw new Error("Concurrency must be a positive integer.");
  const results: R[] = [];
  for (let offset = 0; offset < items.length; offset += concurrency) {
    const wave = items.slice(offset, offset + concurrency);
    const waveResults = await Promise.all(wave.map((item, waveIndex) => mapItem(item, offset + waveIndex)));
    results.push(...waveResults);
    onWaveComplete?.(results.length, items.length);
  }
  return results;
}
