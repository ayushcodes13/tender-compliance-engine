import { execFile as execFileCallback } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);
const OCR_TIMEOUT_MS = 15_000;
const OCR_MAX_BUFFER_BYTES = 8 * 1024 * 1024;

export function resolveTesseractBinary(configured = process.env.TESSERACT_BINARY): string {
  if (configured?.trim()) return configured.trim();
  const homebrewBins = ["/opt/homebrew/opt/tesseract/bin/tesseract", "/usr/local/opt/tesseract/bin/tesseract"];
  return homebrewBins.find((path) => existsSync(path)) ?? "tesseract";
}

export function resolveTesseractLanguage(configured = process.env.TESSERACT_LANG): string {
  const language = configured?.trim() || "eng";
  return /^[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*$/.test(language) ? language : "eng";
}

export type OcrConfidence = "high" | "medium" | "low";

export type OcrWord = {
  start: number;
  end: number;
  text: string;
  bbox: { x: number; y: number; width: number; height: number };
  confidence: number;
  confidenceLevel: OcrConfidence;
};

export type OcrLine = {
  text: string;
  bbox: { x: number; y: number; width: number; height: number };
  confidence: number;
  confidenceLevel: OcrConfidence;
  words: OcrWord[];
};

export type OcrPageText = {
  text: string;
  lines: OcrLine[];
};

export type PopplerPageRenderer = {
  renderPage(pageNumber: number, maxDimension: number, signal?: AbortSignal): Promise<Uint8Array>;
  close(): Promise<void>;
};

export async function isPopplerAvailable(binary = process.env.PDFTOPPM_BINARY || "pdftoppm", signal?: AbortSignal): Promise<boolean> {
  try {
    signal?.throwIfAborted();
    await execFile(binary, ["-v"], { timeout: 3_000, maxBuffer: 64 * 1024, signal });
    return true;
  } catch {
    signal?.throwIfAborted();
    return false;
  }
}

/** Keeps one private PDF copy for the OCR pass and deletes it when the request ends. */
export function createPopplerPageRenderer(
  pdfBytes: Uint8Array,
  binary = process.env.PDFTOPPM_BINARY || "pdftoppm",
): PopplerPageRenderer {
  let directory: string | undefined;
  let inputPath: string | undefined;
  const ensureInput = async () => {
    if (inputPath) return inputPath;
    directory = await mkdtemp(join(tmpdir(), "tce-pdf-render-"));
    inputPath = join(directory, "source.pdf");
    await writeFile(inputPath, pdfBytes, { mode: 0o600 });
    return inputPath;
  };
  return {
    async renderPage(pageNumber, maxDimension, signal) {
      signal?.throwIfAborted();
      if (!Number.isInteger(pageNumber) || pageNumber < 1 || !Number.isInteger(maxDimension) || maxDimension < 1) {
        throw new Error("Invalid PDF page render request.");
      }
      const sourcePath = await ensureInput();
      const prefix = join(directory!, `page-${pageNumber}`);
      await execFile(binary, ["-f", String(pageNumber), "-l", String(pageNumber), "-singlefile", "-scale-to", String(maxDimension), "-png", sourcePath, prefix], {
        timeout: 30_000,
        maxBuffer: 64 * 1024,
        signal,
      });
      signal?.throwIfAborted();
      return readFile(`${prefix}.png`);
    },
    async close() {
      if (directory) await rm(directory, { recursive: true, force: true });
      directory = undefined;
      inputPath = undefined;
    },
  };
}

export type PositionedOcrLine = {
  start: number;
  end: number;
  text: string;
  box: OcrLine["bbox"];
  ocrConfidenceLevel: OcrConfidence;
  words: Array<OcrWord & { start: number; end: number }>;
};

export function buildOcrTextPositionMap(lines: OcrLine[]): {
  text: string;
  rawItemMap: number[];
  positioned: PositionedOcrLine[];
} {
  const rawItemMap: number[] = [];
  const positioned: PositionedOcrLine[] = [];
  let offset = 0;
  for (const line of lines) {
    if (positioned.length) {
      rawItemMap[offset] = -1;
      offset += 1;
    }
    const start = offset;
    offset += line.text.length;
    for (let index = start; index < offset; index += 1) rawItemMap[index] = positioned.length;
    positioned.push({
      start,
      end: offset,
      text: line.text,
      box: line.bbox,
      ocrConfidenceLevel: line.confidenceLevel,
      words: line.words.map((word) => ({ ...word, start: start + word.start, end: start + word.end })),
    });
  }
  return { text: lines.map((line) => line.text).join("\n"), rawItemMap, positioned };
}

function confidenceLevel(confidence: number): OcrConfidence {
  return confidence >= 85 ? "high" : confidence >= 60 ? "medium" : "low";
}

const ENGINEERING_UNITS = new Set([
  "%", "°c", "°f", "k", "mm", "cm", "m", "µm", "um", "nm", "in", "inch", "inches", "ft",
  "pa", "kpa", "mpa", "gpa", "bar", "mbar", "psi", "atm", "torr", "kn", "n", "mn",
  "v", "mv", "kv", "a", "ma", "ka", "w", "mw", "kw", "va", "kva", "hz", "khz", "mhz", "ghz",
  "db", "dbc", "rpm", "rps", "l/s", "l/min", "ml/min", "m³/h", "kg", "g", "mg", "s", "ms", "min", "h", "hr",
]);

function isEngineeringUnit(token: string): boolean {
  const normalized = token.trim().replace(/^[([{]+|[.,;:)}\]]+$/g, "").toLowerCase();
  return ENGINEERING_UNITS.has(normalized);
}

function criticalValueConfidence(words: OcrWord[], average: number): number {
  const critical = new Set<number>();
  words.forEach((word, index) => {
    if (/[0-9<>≤≥±=]/u.test(word.text) || /[+−-]\s*\d/u.test(word.text)) {
      critical.add(index);
      if (isEngineeringUnit(words[index + 1]?.text ?? "")) critical.add(index + 1);
    }
  });
  if (!critical.size) return average;
  return Math.min(...[...critical].map((index) => words[index].confidence));
}

export function parseTesseractTsv(
  tsv: string,
  pageSize: { width: number; height: number },
  imageSize: { width: number; height: number },
): OcrPageText {
  const rows = tsv.split(/\r?\n/).filter(Boolean);
  const header = rows.shift()?.split("\t") ?? [];
  const column = (name: string) => header.indexOf(name);
  const required = ["level", "block_num", "par_num", "line_num", "left", "top", "width", "height", "conf", "text"];
  if (required.some((name) => column(name) < 0) || imageSize.width <= 0 || imageSize.height <= 0) return { text: "", lines: [] };

  const groups = new Map<string, Array<{ text: string; left: number; top: number; right: number; bottom: number; confidence: number }>>();
  for (const row of rows) {
    const cells = row.split("\t");
    if (cells[column("level")] !== "5") continue;
    const text = cells[column("text")]?.trim() ?? "";
    const confidence = Number(cells[column("conf")]);
    const left = Number(cells[column("left")]);
    const top = Number(cells[column("top")]);
    const width = Number(cells[column("width")]);
    const height = Number(cells[column("height")]);
    if (!text || !Number.isFinite(confidence) || confidence < 0
      || ![left, top, width, height].every(Number.isFinite) || width <= 0 || height <= 0) continue;
    const key = ["page_num", "block_num", "par_num", "line_num"].map((name) => cells[column(name)] ?? "").join(":");
    const words = groups.get(key) ?? [];
    words.push({ text, left, top, right: left + width, bottom: top + height, confidence });
    groups.set(key, words);
  }

  const scaleX = pageSize.width / imageSize.width;
  const scaleY = pageSize.height / imageSize.height;
  const lines = [...groups.values()].map((words) => {
    words.sort((left, right) => left.left - right.left);
    const averageConfidence = words.reduce((total, word) => total + word.confidence, 0) / words.length;
    const left = Math.min(...words.map((word) => word.left));
    const top = Math.min(...words.map((word) => word.top));
    const right = Math.max(...words.map((word) => word.right));
    const bottom = Math.max(...words.map((word) => word.bottom));
    let textOffset = 0;
    const positionedWords: OcrWord[] = words.map((word, index) => {
      if (index) textOffset += 1;
      const start = textOffset;
      textOffset += word.text.length;
      return {
        start,
        end: textOffset,
        text: word.text,
        bbox: { x: word.left * scaleX, y: word.top * scaleY, width: (word.right - word.left) * scaleX, height: (word.bottom - word.top) * scaleY },
        confidence: word.confidence,
        confidenceLevel: confidenceLevel(word.confidence),
      };
    });
    const confidence = criticalValueConfidence(positionedWords, averageConfidence);
    return {
      text: words.map((word) => word.text).join(" "),
      bbox: { x: left * scaleX, y: top * scaleY, width: (right - left) * scaleX, height: (bottom - top) * scaleY },
      confidence,
      confidenceLevel: confidenceLevel(confidence),
      words: positionedWords,
      top,
      left,
    };
  }).sort((left, right) => left.top - right.top || left.left - right.left)
    .map(({ top: _top, left: _left, ...line }) => line);

  return { text: lines.map((line) => line.text).join("\n"), lines };
}

export async function isTesseractAvailable(binary = resolveTesseractBinary(), signal?: AbortSignal): Promise<boolean> {
  try {
    signal?.throwIfAborted();
    await execFile(binary, ["--version"], { timeout: 10_000, maxBuffer: 64 * 1024, signal });
    const { stdout } = await execFile(binary, ["--list-langs"], { timeout: 10_000, maxBuffer: 64 * 1024, signal });
    const available = new Set(stdout.split(/\r?\n/).map((line) => line.trim()).filter((line) => /^[A-Za-z0-9_]+$/.test(line)));
    return resolveTesseractLanguage().split("+").every((language) => available.has(language));
  } catch {
    signal?.throwIfAborted();
    return false;
  }
}

/** Runs local OCR on a rendered page image and always removes its private temporary directory. */
export async function recognizePageImage(input: {
  image: Uint8Array;
  imageSize: { width: number; height: number };
  pageSize: { width: number; height: number };
  binary?: string;
  language?: string;
  timeoutMs?: number;
  signal?: AbortSignal;
}): Promise<OcrPageText> {
  const directory = await mkdtemp(join(tmpdir(), "tce-page-ocr-"));
  const imagePath = join(directory, "page.png");
  try {
    input.signal?.throwIfAborted();
    await writeFile(imagePath, input.image, { mode: 0o600 });
    const { stdout } = await execFile(
      input.binary || resolveTesseractBinary(),
      [imagePath, "stdout", "--oem", "1", "--psm", "3", "-l", resolveTesseractLanguage(input.language), "tsv"],
      { timeout: input.timeoutMs ?? OCR_TIMEOUT_MS, maxBuffer: OCR_MAX_BUFFER_BYTES, encoding: "utf8", signal: input.signal },
    );
    input.signal?.throwIfAborted();
    return parseTesseractTsv(stdout, input.pageSize, input.imageSize);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

export function combineOcrConfidence(levels: OcrConfidence[]): OcrConfidence | null {
  if (!levels.length) return null;
  if (levels.includes("low")) return "low";
  if (levels.includes("medium")) return "medium";
  return "high";
}
