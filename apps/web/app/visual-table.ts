export type VisualTableRow = {
  text: string;
  page: number;
  sourceRowHeight?: number;
  sourceTextHeight?: number;
  exportGroupId?: string;
  continuationOfPrevious?: boolean;
};

export type VisualHeadingRow = VisualTableRow & {
  headingPrefix?: string;
  remark?: string;
  mergeWithNext?: boolean;
  rowType?: "section" | "requirement" | "optional_heading";
};

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

/** Reassembles AI-split review requirements only when they came from one source cell. */
export function mergeVisualExportGroups<T extends VisualTableRow>(rows: T[]): T[] {
  const merged: T[] = [];
  for (const row of rows) {
    const previous = merged.at(-1);
    if (row.exportGroupId && previous?.exportGroupId === row.exportGroupId) {
      merged[merged.length - 1] = {
        ...previous,
        text: `${previous.text}\n${row.text}`,
      };
    } else {
      merged.push(row);
    }
  }
  return merged;
}

/** Preserves source order while allowing Word to paginate the response table naturally. */
export function prepareVisualComplianceRows<T extends VisualHeadingRow>(rows: T[]): T[] {
  return mergeVisualHeadingRows(mergeVisualRowContinuations(mergeVisualExportGroups(rows)));
}

/** Applies only an explicit visual-model decision to join a standalone title row with its descriptor. */
export function mergeVisualHeadingRows<T extends VisualHeadingRow>(rows: T[]): T[] {
  const merged: T[] = [];
  for (let index = 0; index < rows.length; index += 1) {
    const current = rows[index];
    const next = rows[index + 1];
    if (current.rowType === "section" && current.mergeWithNext && next && current.page === next.page && !current.remark) {
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

export function discardContainedSuggestions<T extends { quote?: unknown; row_type?: string }>(draftQuotes: string[], suggestions: T[]): T[] {
  const drafts = draftQuotes.map((quote) => quote.replace(/\s+/g, " ").trim());
  return suggestions.filter((suggestion) => {
    if (typeof suggestion.quote !== "string") return false;
    const candidate = suggestion.quote.replace(/\s+/g, " ").trim();
    if (!candidate) return false;
    // A structural label can be a separately formatted heading inside the
    // same source cell as its following requirements. Its words therefore
    // also occur inside the larger draft quote, but the heading still needs
    // its own visible row in the response sheet.
    if (suggestion.row_type === "section" || suggestion.row_type === "optional_heading") return true;
    return !drafts.some((draft) => draft.length > candidate.length && draft.includes(candidate));
  });
}

export function discardContainedSuggestionsByPage<T extends { page?: number; quote?: unknown; row_type?: string }>(
  draftRows: Array<{ page?: number; quote?: unknown }>,
  suggestions: T[],
): T[] {
  const normalize=(quote:string)=>quote.replace(/\s+/g," ").trim();
  return suggestions.filter((suggestion) => {
    if(!Number.isInteger(suggestion.page)||typeof suggestion.quote!=="string")return false;
    const quotes=draftRows.filter(draft=>draft.page===suggestion.page&&typeof draft.quote==="string").map(draft=>draft.quote as string);
    // Recovery has no new source-cell identity. An equal quote is already
    // represented; separately located native cells are retained upstream.
    if(quotes.some(quote=>normalize(quote)===normalize(suggestion.quote as string)))return false;
    return discardContainedSuggestions(quotes,[suggestion]).length>0;
  });
}

/** Exact, individually bordered source cells may legitimately repeat words found in another row. */
export function keepParsedSourceCandidate<T extends { quote?: unknown; row_type?: string; source_cells_exact?: boolean }>(
  candidate: T,
  samePageQuotes: string[],
): boolean {
  return candidate.source_cells_exact === true
    || discardContainedSuggestions(samePageQuotes, [candidate]).length > 0;
}

export function sourceCandidateKey(page: number, quote: string, sourceCells?: string[], sourceRowIndex?: number): string {
  const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
  return `${page}:${sourceRowIndex ?? ""}:${normalize(quote)}:${sourceCells?.length ? normalize(sourceCells.join(" | ")) : ""}`;
}

export function splitSourceQuote(source: string, parts: string[]): string[] {
  const normalized = (value: string) => value.replace(/\s+/g, " ").trim();
  if (parts.length < 2 || parts.some((part) => !part.trim())) return [source];
  return normalized(parts.join(" ")) === normalized(source) ? parts : [source];
}
