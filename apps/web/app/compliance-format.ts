export type HeadingTextParts = { heading: string; remainder: string };

/** Scales measured PDF cell heights into DOCX twips, with reference-sized minimums. */
export function complianceRowHeightTwips(sourceRowHeight: number | undefined, isSection: boolean): number {
  const minimum = isSection ? 236 : 217;
  if (!Number.isFinite(sourceRowHeight) || !sourceRowHeight || sourceRowHeight <= 0) return isSection ? minimum : 443;
  return Math.max(minimum, Math.round(sourceRowHeight * 19.28));
}

/** Reflows PDF visual wraps for Word while retaining actual list items on separate lines. */
export function reflowComplianceText(text: string, preserveLineItems = false): string {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  let output = "";
  for (const line of lines) {
    const listItem = /^[-•]\s/.test(line) || preserveLineItems;
    output += `${output ? (listItem ? "\n" : " ") : ""}${line}`;
  }
  return output;
}

/** Splits a literal heading prefix from a source row for styling only. */
export function splitHeadingPrefix(text: string, headingPrefix?: string): HeadingTextParts | null {
  const prefix = headingPrefix?.trim();
  if (!prefix || !text.trim()) return null;
  const escapedWords = prefix.split(/\s+/).map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const expression = new RegExp(`^\\s*${escapedWords.join("\\s+")}(?=\\s|$)`);
  const match = expression.exec(text);
  if (!match) return null;
  return {
    heading: match[0].trim(),
    remainder: text.slice(match[0].length),
  };
}
