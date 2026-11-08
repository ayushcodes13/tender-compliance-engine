const DATABASE_NAME = "tender-review-local-draft";
const DATABASE_VERSION = 1;
const STORE_NAME = "drafts";
const ACTIVE_DRAFT_ID = "active";
export const MAX_LOCAL_DRAFT_FILE_BYTES = 32 * 1024 * 1024;

type ReviewDraftRecord = {
  id: typeof ACTIVE_DRAFT_ID;
  schemaVersion: typeof DATABASE_VERSION;
  savedAt: number;
  filename: string;
  fileType: string;
  fileLastModified: number;
  fileBlob: Blob;
  documentFingerprint: string;
  analysis: unknown;
  responseSheet: unknown;
  sheetEdited: boolean;
  activeRequirementId: string | null;
  page: number;
};

export type ReviewDraftSummary = {
  filename: string;
  savedAt: number;
  fileBytes: number;
  pageCount: number;
  documentFingerprint: string;
};

export type ReviewDraftInput<TAnalysis, TResponseSheet> = {
  file: File;
  analysis: TAnalysis;
  responseSheet: TResponseSheet;
  sheetEdited: boolean;
  activeRequirementId?: string | null;
  page?: number;
  replaceExisting?: boolean;
};

export type RestoredReviewDraft<TAnalysis, TResponseSheet> = ReviewDraftSummary & {
  file: File;
  analysis: TAnalysis;
  responseSheet: TResponseSheet;
  sheetEdited: boolean;
  activeRequirementId: string | null;
  page: number;
};

export interface ReviewDraftStorage {
  get(): Promise<unknown | undefined>;
  put(record: unknown, allowReplacement?: boolean): Promise<void>;
  delete(): Promise<void>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isHexFingerprint(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

const fingerprintCache = new WeakMap<Blob, Promise<string>>();

async function sha256(file: Blob): Promise<string> {
  const cached = fingerprintCache.get(file);
  if (cached) return cached;
  if (!globalThis.crypto?.subtle) throw new Error("This browser cannot verify the saved tender file.");
  const fingerprintPromise = file.arrayBuffer()
    .then((bytes) => globalThis.crypto.subtle.digest("SHA-256", bytes))
    .then((digest) => Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(""));
  fingerprintCache.set(file, fingerprintPromise);
  return fingerprintPromise;
}

function assertSnapshotMatchesDocument(
  record: ReviewDraftRecord,
  actualFingerprint: string,
): { pageCount: number; documentId: string; versionId: string } {
  const analysis = record.analysis;
  if (!isRecord(analysis) || !isRecord(analysis.document)) {
    throw new Error("The saved review data is incomplete. Keep the original tender and start a new analysis.");
  }
  const document = analysis.document;
  const expectedDocumentId = `doc-${actualFingerprint.slice(0, 24)}`;
  const expectedVersionId = `ver-${actualFingerprint}`;
  const pageCount = analysis.pageCount;
  if (
    document.documentFingerprint !== actualFingerprint
    || record.documentFingerprint !== actualFingerprint
    || document.documentId !== expectedDocumentId
    || document.documentVersionId !== expectedVersionId
    || !Number.isInteger(pageCount)
    || (pageCount as number) < 1
    || pageCount !== document.pageCount
    || !Array.isArray(analysis.requirements)
    || !Array.isArray((record.responseSheet as Record<string, unknown> | null)?.columns)
    || !Array.isArray((record.responseSheet as Record<string, unknown> | null)?.rows)
  ) {
    throw new Error("The saved review does not match this tender file. It has not been restored.");
  }

  const requirements = analysis.requirements;
  const classificationCandidates = Array.isArray(analysis.classificationReviewCandidates) ? analysis.classificationReviewCandidates : [];
  for (const requirement of [...requirements, ...classificationCandidates]) {
    if (!isRecord(requirement) || !Number.isInteger(requirement.page) || (requirement.page as number) < 1 || (requirement.page as number) > (pageCount as number)) {
      throw new Error("A saved source candidate has an invalid physical page reference. It has not been restored.");
    }
    if (requirement.sourceReference !== undefined && requirement.sourceReference !== null) {
      const source = requirement.sourceReference;
      if (!isRecord(source)
        || source.documentId !== expectedDocumentId
        || source.documentVersionId !== expectedVersionId
        || source.documentFingerprint !== actualFingerprint
        || source.physicalPdfPageNumber !== requirement.page) {
        throw new Error("A saved citation does not match the tender identity and page. It has not been restored.");
      }
    }
  }

  return { pageCount: pageCount as number, documentId: expectedDocumentId, versionId: expectedVersionId };
}

function validateRecord(value: unknown): ReviewDraftRecord {
  if (!isRecord(value) || value.schemaVersion !== DATABASE_VERSION || value.id !== ACTIVE_DRAFT_ID) {
    throw new Error("The saved review uses an unsupported format. It has not been changed.");
  }
  const record = value as unknown as ReviewDraftRecord;
  if (
    !(record.fileBlob instanceof Blob)
    || record.fileBlob.size < 1
    || record.fileBlob.size > MAX_LOCAL_DRAFT_FILE_BYTES
    || typeof record.filename !== "string"
    || !record.filename.toLowerCase().endsWith(".pdf")
    || !isHexFingerprint(record.documentFingerprint)
    || typeof record.savedAt !== "number"
    || !Number.isFinite(record.savedAt)
    || typeof record.sheetEdited !== "boolean"
    || !Number.isInteger(record.page)
    || !(record.activeRequirementId === null || typeof record.activeRequirementId === "string")
  ) {
    throw new Error("The saved review is damaged or incomplete. It has not been restored.");
  }
  return record;
}

function summaryFor(record: ReviewDraftRecord, pageCount: number): ReviewDraftSummary {
  return {
    filename: record.filename,
    savedAt: record.savedAt,
    fileBytes: record.fileBlob.size,
    pageCount,
    documentFingerprint: record.documentFingerprint,
  };
}

export async function saveLocalReviewDraft<TAnalysis, TResponseSheet>(
  input: ReviewDraftInput<TAnalysis, TResponseSheet>,
  storage: ReviewDraftStorage = indexedDbReviewDraftStorage(),
): Promise<ReviewDraftSummary> {
  if (!(input.file instanceof Blob) || input.file.size < 1 || input.file.size > MAX_LOCAL_DRAFT_FILE_BYTES || !input.file.name.toLowerCase().endsWith(".pdf")) {
    throw new Error("Only a PDF up to 32 MiB can be saved in this browser.");
  }
  if (!isRecord(input.analysis) || !isRecord(input.analysis.document)) {
    throw new Error("The analysis has no verified tender identity and cannot be saved safely.");
  }

  const fingerprint = await sha256(input.file);
  const record: ReviewDraftRecord = {
    id: ACTIVE_DRAFT_ID,
    schemaVersion: DATABASE_VERSION,
    savedAt: Date.now(),
    filename: input.file.name,
    fileType: input.file.type || "application/pdf",
    fileLastModified: input.file.lastModified,
    fileBlob: input.file,
    documentFingerprint: fingerprint,
    analysis: input.analysis,
    responseSheet: input.responseSheet,
    sheetEdited: input.sheetEdited,
    activeRequirementId: input.activeRequirementId ?? null,
    page: input.page ?? 1,
  };
  const { pageCount } = assertSnapshotMatchesDocument(record, fingerprint);
  const requirements = (input.analysis as Record<string, unknown>).requirements as unknown[];
  if (!Number.isInteger(record.page) || record.page < 1 || record.page > pageCount
    || (record.activeRequirementId !== null && !requirements.some((item) => isRecord(item) && item.id === record.activeRequirementId))) {
    throw new Error("The saved review page is invalid and was not changed.");
  }
  await storage.put(record, input.replaceExisting === true);
  return summaryFor(record, pageCount);
}

export async function getLocalReviewDraftSummary(
  storage: ReviewDraftStorage = indexedDbReviewDraftStorage(),
): Promise<ReviewDraftSummary | null> {
  const value = await storage.get();
  if (value === undefined) return null;
  const record = validateRecord(value);
  const analysis = record.analysis;
  if (!isRecord(analysis) || !Number.isInteger(analysis.pageCount) || (analysis.pageCount as number) < 1) {
    throw new Error("The saved review summary is damaged. It has not been restored.");
  }
  return summaryFor(record, analysis.pageCount as number);
}

export async function loadLocalReviewDraft<TAnalysis, TResponseSheet>(
  storage: ReviewDraftStorage = indexedDbReviewDraftStorage(),
): Promise<RestoredReviewDraft<TAnalysis, TResponseSheet> | null> {
  const value = await storage.get();
  if (value === undefined) return null;
  const record = validateRecord(value);
  const actualFingerprint = await sha256(record.fileBlob);
  const { pageCount } = assertSnapshotMatchesDocument(record, actualFingerprint);
  const requirements = (record.analysis as Record<string, unknown>).requirements as unknown[];
  if (!Number.isInteger(record.page) || record.page < 1 || record.page > pageCount
    || (record.activeRequirementId !== null && !requirements.some((item) => isRecord(item) && item.id === record.activeRequirementId))) {
    throw new Error("The saved review page is invalid and was not restored.");
  }
  const file = new File([record.fileBlob], record.filename, {
    type: record.fileType || "application/pdf",
    lastModified: record.fileLastModified,
  });
  return {
    ...summaryFor(record, pageCount),
    file,
    analysis: record.analysis as TAnalysis,
    responseSheet: record.responseSheet as TResponseSheet,
    sheetEdited: record.sheetEdited,
    activeRequirementId: record.activeRequirementId,
    page: record.page,
  };
}

export async function deleteLocalReviewDraft(
  storage: ReviewDraftStorage = indexedDbReviewDraftStorage(),
): Promise<void> {
  await storage.delete();
}

function indexedDbReviewDraftStorage(): ReviewDraftStorage {
  if (typeof indexedDB === "undefined") throw new Error("Local save/resume is unavailable in this browser.");

  const open = () => new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) request.result.createObjectStore(STORE_NAME, { keyPath: "id" });
    };
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error ?? new Error("The local review database could not be opened."));
    request.onblocked = () => reject(new Error("Another tab is preventing access to the local review database. Close the other Tender Review tab and retry."));
  });

  const get = async () => {
    const db = await open();
    try {
      return await new Promise<unknown | undefined>((resolve, reject) => {
        const transaction = db.transaction(STORE_NAME, "readonly");
        const request = transaction.objectStore(STORE_NAME).get(ACTIVE_DRAFT_ID);
        request.onsuccess = () => resolve(request.result as unknown | undefined);
        request.onerror = () => reject(request.error ?? new Error("The saved review could not be read."));
        transaction.onabort = () => reject(transaction.error ?? new Error("The saved review read was interrupted."));
      });
    } finally {
      db.close();
    }
  };

  const put = async (record: unknown, allowReplacement = false) => {
    const db = await open();
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = db.transaction(STORE_NAME, "readwrite");
        const store = transaction.objectStore(STORE_NAME);
        let replacementBlocked = false;
        const current = store.get(ACTIVE_DRAFT_ID);
        current.onsuccess = () => {
          const next = record as ReviewDraftRecord;
          const existingFingerprint = isRecord(current.result) ? current.result.documentFingerprint : undefined;
          if (existingFingerprint && existingFingerprint !== next.documentFingerprint && !allowReplacement) {
            replacementBlocked = true;
            transaction.abort();
            return;
          }
          store.put(record);
        };
        current.onerror = () => reject(current.error ?? new Error("The existing local review could not be checked."));
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error ?? new Error("The local review could not be saved."));
        transaction.onabort = () => reject(replacementBlocked
          ? new Error("A different tender review is already saved in this browser. Confirm replacement before saving this tender.")
          : transaction.error ?? new Error("The local review save was interrupted."));
      });
    } finally {
      db.close();
    }
  };

  const remove = async () => {
    const db = await open();
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = db.transaction(STORE_NAME, "readwrite");
        transaction.objectStore(STORE_NAME).delete(ACTIVE_DRAFT_ID);
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error ?? new Error("The local review could not be deleted."));
        transaction.onabort = () => reject(transaction.error ?? new Error("The local review deletion was interrupted."));
      });
    } finally {
      db.close();
    }
  };

  return { get, put, delete: remove };
}
