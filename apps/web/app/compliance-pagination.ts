/** Partition a fully built response table into page-sized template groups. */
export function partitionRowsForTemplate<T>(rows: T[], rowCounts: readonly number[]): T[][] | null {
  if (!rowCounts.length || rowCounts.some((count) => !Number.isInteger(count) || count < 1)) return null;
  if (rowCounts.reduce((total, count) => total + count, 0) !== rows.length) return null;

  const pages: T[][] = [];
  let offset = 0;
  for (const count of rowCounts) {
    pages.push(rows.slice(offset, offset + count));
    offset += count;
  }
  return pages;
}
