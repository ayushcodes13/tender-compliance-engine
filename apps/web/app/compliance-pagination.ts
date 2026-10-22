/** Splits a rendered export row at a literal boundary without changing its text or order. */
export function splitRowBeforeLiteral<T extends { text: string }>(
  rows: T[],
  rowMarker: string,
  splitBefore: string,
): T[] | null {
  const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
  const matches = rows.flatMap((row, index) => normalize(row.text).includes(normalize(rowMarker)) ? [index] : []);
  if (matches.length !== 1) return null;
  const index = matches[0];
  const expression = new RegExp(splitBefore.trim().split(/\s+/).map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"));
  const splitMatch = expression.exec(rows[index].text);
  if (!splitMatch || splitMatch.index <= 0) return null;

  const firstText = rows[index].text.slice(0, splitMatch.index).trimEnd();
  const continuationText = rows[index].text.slice(splitMatch.index).trimStart();
  if (!firstText || !continuationText) return null;
  return [
    ...rows.slice(0, index),
    { ...rows[index], text: firstText },
    { ...rows[index], text: continuationText },
    ...rows.slice(index + 1),
  ];
}

/** Keeps a page-leading continuation in the next source row's display entry. */
export function attachLeadingContinuation<T extends { text: string }>(rows: T[]): Array<T & { pageContinuation?: string }> | null {
  if (rows.length < 2 || !rows[0].text.trim() || !rows[1].text.trim()) return null;
  return [
    { ...rows[1], pageContinuation: rows[0].text },
    ...rows.slice(2),
  ];
}

/** Splits rows after ordered literal anchors, returning null when the anchors are ambiguous or absent. */
export function partitionRowsAtMarkers<T extends { text: string }>(
  rows: T[],
  endMarkers: readonly string[],
): T[][] | null {
  if (!endMarkers.length) return null;
  const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
  const pages: T[][] = [];
  let offset = 0;
  for (const marker of endMarkers) {
    const matches = rows.flatMap((row, index) => index >= offset && normalize(row.text).includes(normalize(marker)) ? [index] : []);
    if (matches.length !== 1) return null;
    const end = matches[0] + 1;
    pages.push(rows.slice(offset, end));
    offset = end;
  }
  if (offset >= rows.length) return null;
  pages.push(rows.slice(offset));
  return pages;
}
