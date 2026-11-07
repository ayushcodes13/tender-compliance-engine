export type TextPageAuditInput = {
  page: number;
  text: string;
  knownRows: string[];
};

export type TextPageAuditBatch = {
  pages: TextPageAuditInput[];
  estimatedChars: number;
};

export const TEXT_PAGE_AUDIT_TARGET_CHARS = 60_000;
export const TEXT_PAGE_AUDIT_MAX_CHARS = 180_000;
export const TEXT_PAGE_AUDIT_MAX_PAGES = 4;
export const TEXT_PAGE_AUDIT_MAX_BATCHES = 8;
export const TEXT_PAGE_AUDIT_CONCURRENCY = 3;

function estimateInputChars(page: TextPageAuditInput): number {
  return page.text.length + page.knownRows.reduce((total, row) => total + row.length + 4, 0) + 32;
}

export function batchTextPagesForAudit(pages: TextPageAuditInput[]): {
  batches: TextPageAuditBatch[];
  oversizedPages: number[];
  deferredPages: number[];
} {
  const batches: TextPageAuditBatch[] = [];
  const oversizedPages: number[] = [];
  let current: TextPageAuditInput[] = [];
  let currentChars = 0;

  for (const page of pages) {
    const pageChars = estimateInputChars(page);
    if (pageChars > TEXT_PAGE_AUDIT_MAX_CHARS) {
      oversizedPages.push(page.page);
      continue;
    }
    const exceedsTarget = current.length > 0 && currentChars + pageChars > TEXT_PAGE_AUDIT_TARGET_CHARS;
    const exceedsPages = current.length >= TEXT_PAGE_AUDIT_MAX_PAGES;
    if (exceedsTarget || exceedsPages) {
      batches.push({ pages: current, estimatedChars: currentChars });
      current = [];
      currentChars = 0;
    }
    current.push(page);
    currentChars += pageChars;
    if (pageChars > TEXT_PAGE_AUDIT_TARGET_CHARS) {
      batches.push({ pages: current, estimatedChars: currentChars });
      current = [];
      currentChars = 0;
    }
  }
  if (current.length) batches.push({ pages: current, estimatedChars: currentChars });

  const deferredBatches = batches.slice(TEXT_PAGE_AUDIT_MAX_BATCHES);
  return {
    batches: batches.slice(0, TEXT_PAGE_AUDIT_MAX_BATCHES),
    oversizedPages,
    deferredPages: deferredBatches.flatMap((batch) => batch.pages.map((page) => page.page)),
  };
}
