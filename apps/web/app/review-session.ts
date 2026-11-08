const SESSION_VERSION = 1;
const KDF_ITERATIONS = 600_000;
const MAX_PLAINTEXT_BYTES = 64 * 1024 * 1024;
export const MAX_REVIEW_SESSION_FILE_BYTES = 90 * 1024 * 1024;

const ENVELOPE_ALGORITHM = "AES-256-GCM";
const KDF_ALGORITHM = "PBKDF2-SHA-256";
const AAD = new TextEncoder().encode("tender-review-session:v1:PBKDF2-SHA-256:600000:AES-256-GCM").buffer as ArrayBuffer;

type ReviewAnalysisSnapshot = Record<string, unknown> & {
  filename: string;
  pageCount: number;
  document: Record<string, unknown>;
  requirements: Array<Record<string, unknown>>;
};

export type ReviewSession = {
  version: 1;
  createdAt: string;
  documentFingerprint: string;
  filename: string;
  analysis: ReviewAnalysisSnapshot;
  responseSheet: { columns: unknown[]; rows: unknown[]; layout?: unknown };
  sheetEdited: boolean;
};

type EncryptedEnvelope = {
  format: "tender-review-session";
  version: 1;
  kdf: typeof KDF_ALGORITHM;
  iterations: typeof KDF_ITERATIONS;
  cipher: typeof ENVELOPE_ALGORITHM;
  salt: string;
  iv: string;
  ciphertext: string;
};

function assertCryptoAvailable(): Crypto {
  const provider = globalThis.crypto;
  if (!provider?.subtle || !provider.getRandomValues) throw new Error("Encrypted review sessions require a browser with Web Crypto enabled over HTTPS or localhost.");
  return provider;
}

function assertPassphrase(passphrase: string): void {
  if (typeof passphrase !== "string" || passphrase.length < 12 || passphrase.length > 512) {
    throw new Error("Use a passphrase between 12 and 512 characters.");
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validateSession(value: unknown): ReviewSession {
  if (!isRecord(value) || value.version !== SESSION_VERSION || typeof value.createdAt !== "string"
      || Number.isNaN(Date.parse(value.createdAt)) || typeof value.filename !== "string"
      || value.filename.length < 1 || value.filename.length > 255 || !isRecord(value.analysis)
      || !isRecord(value.responseSheet) || !Array.isArray(value.responseSheet.columns)
      || !Array.isArray(value.responseSheet.rows) || typeof value.sheetEdited !== "boolean") {
    throw new Error("The review session file has an unsupported or invalid structure.");
  }

  const analysis = value.analysis;
  const document = isRecord(analysis.document) ? analysis.document : null;
  const fingerprint = document?.documentFingerprint;
  const requirements = analysis.requirements;
  if (typeof fingerprint !== "string" || !/^[a-f0-9]{64}$/.test(fingerprint) || value.documentFingerprint !== fingerprint
      || analysis.filename !== value.filename
      || document?.documentId !== `doc-${fingerprint.slice(0, 24)}`
      || document?.documentVersionId !== `ver-${fingerprint}`
      || document?.pageCount !== analysis.pageCount
      || !Number.isInteger(analysis.pageCount) || (analysis.pageCount as number) < 1 || (analysis.pageCount as number) > 120
      || !Array.isArray(analysis.requirements) || analysis.requirements.length > 400
      || value.responseSheet.columns.length < 1 || value.responseSheet.columns.length > 64
      || value.responseSheet.rows.length > 400) {
    throw new Error("The review session file is missing valid tender identity or review data.");
  }

  const requirementIds = new Set<string>();
  for (const requirement of requirements as unknown[]) {
    if (!isRecord(requirement) || typeof requirement.id !== "string" || requirement.id.length > 512
        || typeof requirement.text !== "string" || typeof requirement.quote !== "string"
        || typeof requirement.page !== "number" || !Number.isInteger(requirement.page)
        || requirement.page < 1 || requirement.page > (analysis.pageCount as number)
        || typeof requirement.reviewed !== "boolean" || requirementIds.has(requirement.id)) {
      throw new Error("The review session contains a requirement without valid source identity.");
    }
    requirementIds.add(requirement.id);
    const sourceReference = requirement.sourceReference;
    if (!isRecord(sourceReference) || sourceReference.documentId !== document?.documentId
        || sourceReference.documentVersionId !== document?.documentVersionId
        || sourceReference.documentFingerprint !== fingerprint
        || sourceReference.physicalPdfPageNumber !== requirement.page
        || typeof sourceReference.sourceText !== "string" || !Array.isArray(sourceReference.sourceElementIds)
        || !["exact", "approximate"].includes(String(sourceReference.locationPrecision))
        || sourceReference.bboxCoordinateSystem !== "pdfjs-viewport-scale-1") {
      throw new Error("The review session contains a requirement without valid source identity.");
    }
    const box = sourceReference.bbox;
    if (box !== null && (!isRecord(box)
        || !["x", "y", "width", "height"].every((key) => typeof box[key] === "number" && Number.isFinite(box[key]) && (box[key] as number) >= 0)
        || (box.width as number) <= 0 || (box.height as number) <= 0)) {
      throw new Error("The review session contains an invalid source location.");
    }
  }

  const validColumnRoles = new Set(["heading", "requirement", "source", "response", "page", "compliance", "deviation"]);
  for (const column of value.responseSheet.columns) {
    if (!isRecord(column) || typeof column.header !== "string" || column.header.length > 255
        || typeof column.role !== "string" || !validColumnRoles.has(column.role)) {
      throw new Error("The review session contains an invalid response sheet column.");
    }
  }

  const rowIds = new Set<string>();
  for (const row of value.responseSheet.rows) {
    if (!isRecord(row) || !Array.isArray(row.values) || row.values.length !== value.responseSheet.columns.length
        || typeof row.id !== "string" || typeof row.sourceRequirementId !== "string"
        || !Array.isArray(row.sourceRequirementIds) || row.sourceRequirementIds.some((id) => typeof id !== "string")
        || row.values.some((cell) => typeof cell !== "string")
        || rowIds.has(row.id) || !requirementIds.has(row.sourceRequirementId)
        || (row.sourceRequirementIds as string[]).some((id) => !requirementIds.has(id))) {
      throw new Error("The review session file contains an invalid response sheet row.");
    }
    rowIds.add(row.id);
  }

  return value as unknown as ReviewSession;
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  return btoa(binary);
}

function fromBase64(encoded: unknown, maxBytes: number): Uint8Array {
  if (typeof encoded !== "string" || encoded.length > Math.ceil(maxBytes * 4 / 3) + 8 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) {
    throw new Error("The review session file is too large or malformed.");
  }
  const binary = atob(encoded);
  if (binary.length > maxBytes) throw new Error("The review session file is too large.");
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function asArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(new ArrayBuffer(bytes.byteLength));
  copy.set(bytes);
  return copy.buffer;
}

async function deriveKey(passphrase: string, salt: Uint8Array, cryptoProvider: Crypto): Promise<CryptoKey> {
  const material = await cryptoProvider.subtle.importKey("raw", asArrayBuffer(new TextEncoder().encode(passphrase)), "PBKDF2", false, ["deriveKey"]);
  return cryptoProvider.subtle.deriveKey(
    { name: "PBKDF2", salt: asArrayBuffer(salt), iterations: KDF_ITERATIONS, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function encryptReviewSession(input: Omit<ReviewSession, "version" | "createdAt" | "documentFingerprint" | "filename">, passphrase: string, identity: { documentFingerprint: string; filename: string }): Promise<Blob> {
  assertPassphrase(passphrase);
  const cryptoProvider = assertCryptoAvailable();
  const session = validateSession({ ...input, version: SESSION_VERSION, createdAt: new Date().toISOString(), ...identity });
  const plaintext = new TextEncoder().encode(JSON.stringify(session));
  if (plaintext.byteLength > MAX_PLAINTEXT_BYTES) throw new Error("This review session is too large to save in a portable file.");
  const salt = cryptoProvider.getRandomValues(new Uint8Array(16));
  const iv = cryptoProvider.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(passphrase, salt, cryptoProvider);
  const ciphertext = await cryptoProvider.subtle.encrypt({ name: "AES-GCM", iv: asArrayBuffer(iv), additionalData: AAD, tagLength: 128 }, key, asArrayBuffer(plaintext));
  const envelope: EncryptedEnvelope = {
    format: "tender-review-session",
    version: SESSION_VERSION,
    kdf: KDF_ALGORITHM,
    iterations: KDF_ITERATIONS,
    cipher: ENVELOPE_ALGORITHM,
    salt: toBase64(salt),
    iv: toBase64(iv),
    ciphertext: toBase64(new Uint8Array(ciphertext)),
  };
  const blob = new Blob([JSON.stringify(envelope)], { type: "application/vnd.tender-review-session+json" });
  if (blob.size > MAX_REVIEW_SESSION_FILE_BYTES) throw new Error("This review session is too large to save in a portable file.");
  return blob;
}

export async function decryptReviewSession(file: File, passphrase: string): Promise<ReviewSession> {
  assertPassphrase(passphrase);
  if (file.size > MAX_REVIEW_SESSION_FILE_BYTES) throw new Error("The review session file is too large.");
  const cryptoProvider = assertCryptoAvailable();
  let envelope: unknown;
  try {
    envelope = JSON.parse(await file.text());
  } catch {
    throw new Error("This is not a readable Tender Review session file.");
  }
  if (!isRecord(envelope) || envelope.format !== "tender-review-session" || envelope.version !== SESSION_VERSION
      || envelope.kdf !== KDF_ALGORITHM || envelope.iterations !== KDF_ITERATIONS || envelope.cipher !== ENVELOPE_ALGORITHM) {
    throw new Error("This review session uses an unsupported format or cryptographic setting.");
  }

  const salt = fromBase64(envelope.salt, 16);
  const iv = fromBase64(envelope.iv, 12);
  if (salt.byteLength !== 16 || iv.byteLength !== 12) throw new Error("The review session file is malformed.");
  const ciphertext = fromBase64(envelope.ciphertext, MAX_PLAINTEXT_BYTES + 16);
  try {
    const key = await deriveKey(passphrase, salt, cryptoProvider);
    const plaintext = await cryptoProvider.subtle.decrypt({ name: "AES-GCM", iv: asArrayBuffer(iv), additionalData: AAD, tagLength: 128 }, key, asArrayBuffer(ciphertext));
    return validateSession(JSON.parse(new TextDecoder().decode(plaintext)));
  } catch {
    throw new Error("The passphrase is incorrect or the review session file was changed.");
  }
}

export async function verifyReviewSessionSource(file: Blob, expectedFingerprint: string): Promise<boolean> {
  if (!/^[a-f0-9]{64}$/.test(expectedFingerprint)) return false;
  const cryptoProvider = assertCryptoAvailable();
  const digest = new Uint8Array(await cryptoProvider.subtle.digest("SHA-256", await file.arrayBuffer()));
  const fingerprint = [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return fingerprint === expectedFingerprint;
}
