export type SourceObligationGroupRole = "parent" | "member";

export type SourceObligationGroupReference = {
  id: string;
  role: SourceObligationGroupRole;
  parentCandidateId: string;
  memberOrder: number;
};

export type SourceObligationGroupCandidate = {
  candidateId: string;
  page: number;
  quote: string;
  sourceQuote: string;
  rowType?: string;
  sourceSpan: { startOffset: number; endOffset: number } | null;
};

export type SourceObligationGroupTextElement = {
  id: string;
  text: string;
  startOffset: number;
  endOffset: number;
  bbox: { x: number; y: number; width: number; height: number } | null;
};

export type SourceObligationGroup = {
  id: string;
  page: number;
  parentCandidateId: string;
  members: Array<{ candidateId: string; role: SourceObligationGroupRole; memberOrder: number; sourceSpan: { startOffset: number; endOffset: number } }>;
};

const SERVICE_COMMITMENT_CONTEXT = /\b(?:annual maintenance contract|\bamc\b|maintenance contract|service contract|after[ -]sales service|service support|warranty support)\b/i;
const COMMITMENT_ACTION = /\b(?:shall|must|will|include|includes|provide|provides|quote|quoted|is required to|undertake|undertakes)\b/i;
const INTRODUCER_SUBJECT = /^\s*(?:the\s+)?(?:supplier|vendor|manufacturer|oem|contractor|quote|quotation)\b/i;
const GROUPABLE_ROW_TYPES = new Set(["requirement", "instruction", "ambiguous", "unclassified"]);

function isServiceCommitmentIntroducer(candidate: SourceObligationGroupCandidate): boolean {
  const quote = candidate.sourceQuote.replace(/\s+/g, " ").trim();
  return GROUPABLE_ROW_TYPES.has(candidate.rowType ?? "unclassified")
    && INTRODUCER_SUBJECT.test(quote)
    && /:\s*$/.test(quote)
    && SERVICE_COMMITMENT_CONTEXT.test(quote)
    && COMMITMENT_ACTION.test(quote);
}

function isListSeparator(value: string): boolean {
  return /^[\s,;]*(?:(?:and|or)[\s,;]*)?$/i.test(value);
}

function occursExactlyOnce(sourceText: string, quote: string): boolean {
  const first = sourceText.indexOf(quote);
  return first >= 0 && sourceText.indexOf(quote, first + 1) < 0;
}

// A bullet may introduce *another item in the same list*, not a new
// independent clause. Require an explicit actor/action at the next boundary
// rather than promoting a partial list on the presence of a bullet alone.
function beginsIndependentClause(text: string): boolean {
  const clause = text.trimStart();
  return /^(?:the\s+)?(?:supplier|vendor|manufacturer|oem|contractor|purchaser|buyer|institute|bidder)\b.{0,160}\b(?:shall|must|will|should|is required to|is responsible for|undertakes? to)\b/i.test(clause)
    || /^(?:an?|the)\s+(?:undertaking|declaration|certificate)\b.{0,100}\b(?:must|shall|will|is required to)\b/i.test(clause);
}

function isDefiniteListBoundary(sourceText: string, endOffset: number, elements: SourceObligationGroupTextElement[]): boolean {
  const tail = sourceText.slice(endOffset);
  const literalBoundary = tail.match(/^\s*(?:[.;]\s*)?(?:\r?\n\s*[○◦●▪•\u2022\u25cb\u25e6\u25aa\u25cf]|[○◦●▪•\u2022\u25cb\u25e6\u25aa\u25cf])/u);
  // End-of-page is not proof that a list is complete: its remaining items
  // may continue onto the next physical PDF page.
  if (literalBoundary) {
    // Find the source text after the bullet, not just the marker.
    const marker = /[○◦●▪•\u2022\u25cb\u25e6\u25aa\u25cf]/u.exec(tail);
    return Boolean(marker && beginsIndependentClause(tail.slice(marker.index + marker[0].length)));
  }

  // PDF.js may expose a hollow-circle list marker as a standalone "o" text
  // block. Treat it as a boundary only when parser geometry places it left of
  // the following text on the same baseline; a prose letter "o" is not enough.
  const marker = elements.find((element) => element.startOffset >= endOffset
    && element.startOffset <= endOffset + 4
    && /^o$/i.test(element.text.trim())
    && element.bbox !== null);
  if (!marker || !/^\s*$/.test(sourceText.slice(endOffset, marker.startOffset))) return false;
  const nextText = elements.find((element) => element.startOffset >= marker.endOffset && element.text.trim().length > 0);
  if (!nextText?.bbox || !marker.bbox) return false;
  const sameBaseline = Math.abs(nextText.bbox.y - marker.bbox.y) <= Math.max(marker.bbox.height, nextText.bbox.height, 3);
  const indentedAfterMarker = nextText.bbox.x > marker.bbox.x + Math.max(4, marker.bbox.width);
  const onlySpacingBetween = /^\s*$/.test(sourceText.slice(marker.endOffset, nextText.startOffset));
  return sameBaseline && indentedAfterMarker && onlySpacingBetween
    && beginsIndependentClause(sourceText.slice(marker.endOffset));
}

/**
 * Links a source-backed obligation introducer to its immediately following
 * list items only when every span is unique, ordered, complete, and separated
 * exclusively by list punctuation/whitespace. It never merges source quotes.
 */
export function groupSourceObligationCandidates(input: {
  documentFingerprint: string;
  page: number;
  sourceText: string;
  sourceElements?: SourceObligationGroupTextElement[];
  candidates: SourceObligationGroupCandidate[];
  eligibleCandidateIds: ReadonlySet<string>;
}): SourceObligationGroup[] {
  if (!Number.isInteger(input.page) || input.page < 1 || !input.documentFingerprint || !input.sourceText) return [];

  const located = input.candidates
    .filter((candidate) => candidate.page === input.page && input.eligibleCandidateIds.has(candidate.candidateId)
      && candidate.sourceSpan !== null && candidate.quote.trim() && candidate.rowType !== "section"
      && candidate.rowType !== "optional_heading" && candidate.rowType !== "header")
    .map((candidate) => ({ ...candidate, sourceSpan: candidate.sourceSpan! }))
    .filter((candidate) => Number.isInteger(candidate.sourceSpan.startOffset)
      && Number.isInteger(candidate.sourceSpan.endOffset)
      && candidate.sourceSpan.startOffset >= 0
      && candidate.sourceSpan.endOffset > candidate.sourceSpan.startOffset
      && candidate.sourceSpan.endOffset <= input.sourceText.length
      && occursExactlyOnce(input.sourceText, candidate.sourceQuote)
      && input.sourceText.slice(candidate.sourceSpan.startOffset, candidate.sourceSpan.endOffset) === candidate.sourceQuote);

  const ordered = located.sort((left, right) => left.sourceSpan.startOffset - right.sourceSpan.startOffset
    || left.sourceSpan.endOffset - right.sourceSpan.endOffset);
  const groups: SourceObligationGroup[] = [];
  const claimed = new Set<string>();

  for (const parent of ordered) {
    if (claimed.has(parent.candidateId) || !isServiceCommitmentIntroducer(parent)) continue;
    const parentEnd = parent.sourceSpan.endOffset;
    const children: typeof ordered = [];
    let cursor = parentEnd;

    for (const candidate of ordered) {
      if (candidate.sourceSpan.startOffset < parentEnd || candidate.candidateId === parent.candidateId) continue;
      if (claimed.has(candidate.candidateId)) break;
      const gap = input.sourceText.slice(cursor, candidate.sourceSpan.startOffset);
      const isFirstChild = children.length === 0;
      if (isFirstChild ? !/^\s*$/.test(gap) : !isListSeparator(gap)) break;
      if (candidate.sourceSpan.startOffset < cursor) break;
      children.push(candidate);
      cursor = candidate.sourceSpan.endOffset;
      if (isDefiniteListBoundary(input.sourceText, cursor, input.sourceElements ?? [])) break;
    }

    if (children.length === 0 || !isDefiniteListBoundary(input.sourceText, cursor, input.sourceElements ?? [])) continue;
    const groupId = `sog-${input.documentFingerprint.slice(0, 16)}-p${input.page}-o${parent.sourceSpan.startOffset}`;
    const orderedMembers = [parent, ...children];
    const members = orderedMembers.map((candidate, memberOrder) => ({
      candidateId: candidate.candidateId,
      role: memberOrder === 0 ? "parent" as const : "member" as const,
      memberOrder,
      sourceSpan: candidate.sourceSpan,
    }));
    groups.push({ id: groupId, page: input.page, parentCandidateId: parent.candidateId, members });
    for (const member of members) claimed.add(member.candidateId);
  }

  return groups;
}

/** Places each validated source list together in its source order in a candidate queue. */
export function orderCandidatesBySourceObligationGroups<T>(input: {
  candidates: T[];
  groups: SourceObligationGroup[];
  candidateId: (candidate: T) => string | undefined;
}): T[] {
  let ordered = [...input.candidates];
  for (const group of input.groups) {
    const byId = new Map(ordered.map((candidate) => [input.candidateId(candidate), candidate]));
    const members = group.members.map((member) => byId.get(member.candidateId)).filter((candidate): candidate is T => candidate !== undefined);
    if (members.length < 2) continue;
    const memberSet = new Set(members);
    const indices = members.map((candidate) => ordered.indexOf(candidate)).filter((index) => index >= 0);
    if (indices.length !== members.length) continue;
    const firstIndex = Math.min(...indices);
    const remaining = ordered.filter((candidate) => !memberSet.has(candidate));
    remaining.splice(Math.min(firstIndex, remaining.length), 0, ...members);
    ordered = remaining;
  }
  return ordered;
}
