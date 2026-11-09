#!/usr/bin/env node
import { createHash } from "node:crypto";
import { execFile as execFileCallback } from "node:child_process";
import { readFile, readdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);

function parseArguments(args) {
  const options = { examples: "examples", manifest: "benchmarks/phase-1-v2-corpus.json" };
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === "--examples" && args[index + 1]) options.examples = args[++index];
    else if (args[index] === "--manifest" && args[index + 1]) options.manifest = args[++index];
    else throw new Error("Usage: node benchmarks/scripts/verify-phase1-v2-corpus.mjs [--examples directory] [--manifest file.json]");
  }
  return options;
}

export function pageCountFromPdfInfo(output, fileName = "PDF") {
  const count = Number(/^Pages:\s+(\d+)$/mu.exec(output)?.[1]);
  if (!Number.isSafeInteger(count) || count < 1) throw new Error(`${fileName}: pdfinfo did not return a valid page count.`);
  return count;
}

export function countTextBearingPages(output, expectedPages, fileName = "PDF") {
  const pages = output.split("\f");
  while (pages.length > expectedPages && !pages.at(-1)?.trim()) pages.pop();
  if (pages.length !== expectedPages) throw new Error(`${fileName}: pdftotext returned ${pages.length} page segments; expected ${expectedPages}.`);
  return pages.filter((page) => page.trim().length > 0).length;
}

async function inspectPdf(examplesDirectory, document) {
  const path = join(examplesDirectory, document.fileName);
  const bytes = await readFile(path);
  if (createHash("sha256").update(bytes).digest("hex") !== document.sha256) throw new Error(`${document.fileName}: SHA-256 does not match the corpus manifest.`);
  if (bytes.byteLength !== document.bytes) throw new Error(`${document.fileName}: byte length does not match the corpus manifest.`);

  const { stdout: info } = await execFile("pdfinfo", [path], { maxBuffer: 128 * 1024, encoding: "utf8" });
  const physicalPages = pageCountFromPdfInfo(info, document.fileName);
  if (physicalPages !== document.physicalPages) throw new Error(`${document.fileName}: physical page count does not match the corpus manifest.`);

  const { stdout: text } = await execFile("pdftotext", ["-layout", "-enc", "UTF-8", path, "-"], {
    maxBuffer: 64 * 1024 * 1024,
    encoding: "utf8",
  });
  if (countTextBearingPages(text, physicalPages, document.fileName) !== document.textBearingPages) {
    throw new Error(`${document.fileName}: text-bearing page count does not match the corpus manifest.`);
  }
}

export function validateManifest(manifest, fileNames) {
  if (manifest.schemaVersion !== 1 || !Array.isArray(manifest.documents) || !manifest.documents.length) {
    throw new Error("The corpus manifest has an unsupported schema or no documents.");
  }
  const names = manifest.documents.map((document) => document.fileName);
  if (new Set(names).size !== names.length) throw new Error("The corpus manifest contains duplicate file names.");
  if (names.some((name) => typeof name !== "string" || !name.endsWith(".pdf"))) throw new Error("Every corpus document must name a PDF file.");
  if (names.length !== fileNames.length || names.some((name) => !fileNames.includes(name)) || fileNames.some((name) => !names.includes(name))) {
    throw new Error("The corpus manifest and examples directory do not contain the same PDF set.");
  }

  const groups = new Map();
  const fingerprints = new Map();
  for (const document of manifest.documents) {
    if (document.split !== "development") throw new Error(`${document.fileName}: repository examples must remain in the development split.`);
    if (typeof document.familyGroupId !== "string" || !document.familyGroupId.trim()) throw new Error(`${document.fileName}: familyGroupId is required.`);
    if (groups.has(document.familyGroupId) && groups.get(document.familyGroupId) !== document.split) {
      throw new Error(`${document.fileName}: a document family is split across data splits.`);
    }
    if (!/^[a-f0-9]{64}$/u.test(document.sha256) || !Number.isSafeInteger(document.bytes) || document.bytes < 1) {
      throw new Error(`${document.fileName}: a valid SHA-256 and byte count are required.`);
    }
    if (fingerprints.has(document.sha256) && fingerprints.get(document.sha256) !== document.split) {
      throw new Error(`${document.fileName}: an identical PDF fingerprint is split across data splits.`);
    }
    groups.set(document.familyGroupId, document.split);
    fingerprints.set(document.sha256, document.split);
  }
  if (manifest.inventoryMethod?.sourceContentStored !== false) throw new Error("The corpus inventory must not store source text.");
  if (!Array.isArray(manifest.splitPolicy?.validation) || manifest.splitPolicy.validation.length !== 0
      || !Array.isArray(manifest.splitPolicy?.lockedEvaluation) || manifest.splitPolicy.lockedEvaluation.length !== 0) {
    throw new Error("This initial corpus inventory must not label a validation or locked evaluation set.");
  }
  if (!Array.isArray(manifest.previouslyUsedExternalTenders)) throw new Error("Previously used external tenders must be listed explicitly.");
  for (const external of manifest.previouslyUsedExternalTenders ?? []) {
    if (external.split !== "development" || !/^[a-f0-9]{64}$/u.test(external.sha256)) {
      throw new Error(`${external.id}: known previously used tenders must be fingerprinted development data.`);
    }
  }
}

export async function main() {
  const options = parseArguments(process.argv.slice(2));
  const examplesDirectory = resolve(options.examples);
  const manifest = JSON.parse(await readFile(resolve(options.manifest), "utf8"));
  const fileNames = (await readdir(examplesDirectory)).filter((name) => name.toLowerCase().endsWith(".pdf")).sort();
  validateManifest(manifest, fileNames);
  for (const document of manifest.documents) await inspectPdf(examplesDirectory, document);

  const summary = {
    passed: true,
    corpusId: manifest.corpusId,
    repositoryPdfs: manifest.documents.length,
    uniqueSha256Fingerprints: new Set(manifest.documents.map((document) => document.sha256)).size,
    familyGroups: new Set(manifest.documents.map((document) => document.familyGroupId)).size,
    physicalPages: manifest.documents.reduce((sum, document) => sum + document.physicalPages, 0),
    textBearingPages: manifest.documents.reduce((sum, document) => sum + document.textBearingPages, 0),
    splits: {
      development: manifest.documents.length + manifest.previouslyUsedExternalTenders.length,
      validation: manifest.splitPolicy.validation.length,
      lockedEvaluation: manifest.splitPolicy.lockedEvaluation.length,
    },
    sourceTextWritten: false,
  };
  process.stdout.write(`${JSON.stringify(summary)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : "Corpus verification failed."}\n`);
    process.exitCode = 1;
  });
}
