export type VisualTableRow = {
  text: string;
  page: number;
  sourceRowHeight?: number;
  sourceTextHeight?: number;
  continuationOfPrevious?: boolean;
};

export type VisualHeadingRow = VisualTableRow & {
  headingPrefix?: string;
  remark?: string;
  mergeWithNext?: boolean;
};

/** Keeps DOCX table chunks aligned with the source PDF pages they came from. */
export function groupVisualRowsByPage<T extends VisualTableRow>(rows: T[]): T[][] {
  const groups: T[][] = [];
  for (const row of rows) {
    const current = groups.at(-1);
    if (current && current[0].page === row.page) current.push(row);
    else groups.push([row]);
  }
  return groups;
}

export function mergeVisualRowContinuations<T extends VisualTableRow>(rows: T[]): T[] {
  const merged: T[] = [];
  for (const row of rows) {
    const previous = merged.at(-1);
    if (row.continuationOfPrevious && previous && row.page === previous.page + 1) {
      merged[merged.length - 1] = { ...previous, text: `${previous.text}\n${row.text}` };
      if (previous.sourceTextHeight !== undefined && row.sourceTextHeight !== undefined) {
        merged[merged.length - 1].sourceRowHeight = previous.sourceTextHeight + row.sourceTextHeight;
      } else if (previous.sourceRowHeight !== undefined && row.sourceRowHeight !== undefined) {
        merged[merged.length - 1].sourceRowHeight = previous.sourceRowHeight + row.sourceRowHeight;
      }
    } else {
      merged.push(row);
    }
  }
  return merged;
}

/** Applies only an explicit visual-model decision to join a standalone title row with its descriptor. */
export function mergeVisualHeadingRows<T extends VisualHeadingRow>(rows: T[]): T[] {
  const merged: T[] = [];
  for (let index = 0; index < rows.length; index += 1) {
    const current = rows[index];
    const next = rows[index + 1];
    if (current.mergeWithNext && next && current.page === next.page && !current.remark) {
      merged.push({
        ...current,
        text: `${current.text} ${next.text}`,
        ...(current.sourceRowHeight !== undefined || next.sourceRowHeight !== undefined
          ? { sourceRowHeight: current.sourceRowHeight !== undefined && next.sourceRowHeight !== undefined
            ? current.sourceRowHeight + next.sourceRowHeight
            : current.sourceRowHeight ?? next.sourceRowHeight }
          : {}),
        remark: next.remark ?? current.remark,
        mergeWithNext: false,
      } as T);
      index += 1;
    } else {
      merged.push(current);
    }
  }
  return merged;
}

export function discardContainedSuggestions<T extends { quote?: unknown }>(draftQuotes: string[], suggestions: T[]): T[] {
  const drafts = draftQuotes.map((quote) => quote.replace(/\s+/g, " ").trim().toLocaleLowerCase());
  return suggestions.filter((suggestion) => {
    if (typeof suggestion.quote !== "string") return false;
    const candidate = suggestion.quote.replace(/\s+/g, " ").trim().toLocaleLowerCase();
    return candidate && !drafts.some((draft) => draft.length > candidate.length && draft.includes(candidate));
  });
}

export function splitSourceQuote(source: string, parts: string[]): string[] {
  const normalized = (value: string) => value.replace(/\s+/g, " ").trim();
  if (parts.length < 2 || parts.some((part) => !part.trim())) return [source];
  return normalized(parts.join(" ")) === normalized(source) ? parts : [source];
}
