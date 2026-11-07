#!/usr/bin/env node
import { createHash } from "node:crypto";
import { execFile as execFileCallback } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);

function parseArguments(args) {
  const parsed = { source: "", annotations: [] };
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === "--source" && args[index + 1]) parsed.source = args[++index];
    else if (args[index] === "--annotation" && args[index + 1]) parsed.annotations.push(args[++index]);
    else throw new Error("Usage: node benchmarks/scripts/verify-golden-anchors.mjs --source tender.pdf --annotation gold.json [--annotation more-gold.json]");
  }
  if (!parsed.source || parsed.annotations.length === 0) {
    throw new Error("Usage: node benchmarks/scripts/verify-golden-anchors.mjs --source tender.pdf --annotation gold.json [--annotation more-gold.json]");
  }
  return parsed;
}

function normalizeWhitespace(value) {
  return value.replace(/\s+/gu, " ").trim();
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  const pdf = await readFile(args.source);
  const fingerprint = createHash("sha256").update(pdf).digest("hex");
  const { stdout: pdfInfo } = await execFile("pdfinfo", [args.source], { maxBuffer: 128 * 1024 });
  const pageCount = Number(/^Pages:\s+(\d+)$/mu.exec(pdfInfo)?.[1]);
  if (!Number.isInteger(pageCount) || pageCount < 1) throw new Error("Could not read a valid page count from pdfinfo.");
  const { stdout: extractedText } = await execFile("pdftotext", ["-layout", "-enc", "UTF-8", args.source, "-"], { maxBuffer: 32 * 1024 * 1024, encoding: "utf8" });
  const pages = extractedText.split("\f");
  while (pages.length > pageCount && !pages.at(-1)?.trim()) pages.pop();
  if (pages.length !== pageCount) throw new Error(`pdftotext returned ${pages.length} page segments for a ${pageCount}-page PDF.`);

  const reports = [];
  for (const annotationPath of args.annotations) {
    const annotation = JSON.parse(await readFile(annotationPath, "utf8"));
    if (annotation.sourceSha256 !== fingerprint) {
      throw new Error(`${annotationPath}: source SHA-256 does not match the PDF.`);
    }
    const cases = annotation.cases;
    if (!Array.isArray(cases) || cases.length === 0) throw new Error(`${annotationPath}: expected a non-empty cases array.`);
    let anchorCount = 0;
    for (const [index, item] of cases.entries()) {
      const pageNumber = item.page ?? annotation.physicalPdfPage;
      if (!Number.isInteger(pageNumber) || pageNumber < 1 || pageNumber > pageCount) {
        throw new Error(`${annotationPath}: case ${index + 1} has an invalid or unknown page number.`);
      }
      const rawAnchors = item.sourceAnchors ?? item.sourceAnchor;
      const anchors = typeof rawAnchors === "string" ? [rawAnchors] : rawAnchors;
      if (!Array.isArray(anchors) || anchors.length === 0 || anchors.some((anchor) => typeof anchor !== "string" || !anchor.trim())) {
        throw new Error(`${annotationPath}: case ${item.caseId ?? item.id ?? index + 1} has no sourceAnchor(s).`);
      }
      const pageText = normalizeWhitespace(pages[pageNumber - 1]);
      for (const anchor of anchors) {
        if (!pageText.includes(normalizeWhitespace(anchor))) {
          throw new Error(`${annotationPath}: source anchor not found on physical page ${pageNumber} (case ${item.caseId ?? item.id ?? index + 1}).`);
        }
        anchorCount += 1;
      }
    }
    reports.push({ file: annotationPath, cases: cases.length, sourceAnchorsVerified: anchorCount });
  }
  process.stdout.write(`${JSON.stringify({ passed: true, sourceSha256: fingerprint, pageCount, annotations: reports })}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : "Source-anchor verification failed."}\n`);
  process.exitCode = 1;
});
