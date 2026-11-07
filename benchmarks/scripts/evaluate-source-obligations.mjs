#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export function normalizeSourceText(value) {
  return value.replace(/\s+/gu, " ").trim();
}

function getOutputPage(row) {
  const page = row?.sourceReference?.physicalPdfPageNumber ?? row?.page;
  return Number.isInteger(page) && page > 0 ? page : null;
}

function getSavedAnalysis(output) {
  return output?.analysis && typeof output.analysis === "object" ? output.analysis : output;
}

function getOutputFingerprint(output) {
  const analysis = getSavedAnalysis(output);
  return output?.sourceSha256 ?? output?.documentFingerprint
    ?? analysis?.sourceSha256 ?? analysis?.documentFingerprint ?? analysis?.document?.documentFingerprint;
}

function validateInputs(annotation, output, trace) {
  if (!annotation || typeof annotation !== "object" || !Array.isArray(annotation.cases) || annotation.cases.length === 0) {
    throw new Error("Source annotation must contain a non-empty cases array.");
  }
  if (!/^[a-f0-9]{64}$/iu.test(annotation.sourceSha256 ?? "")) {
    throw new Error("Source annotation must contain a SHA-256 fingerprint.");
  }
  if (getOutputFingerprint(output) !== annotation.sourceSha256) {
    throw new Error("Output source SHA-256 does not match the golden annotation.");
  }
  if (!Array.isArray(getSavedAnalysis(output)?.requirements)) {
    throw new Error("Output artifact must contain a requirements array.");
  }
  if (trace && (trace.documentFingerprint !== annotation.sourceSha256 || !Array.isArray(trace.candidates)
    || trace.candidates.some((candidate) => candidate.documentFingerprint !== annotation.sourceSha256))) {
    throw new Error("Forensic trace must match the annotation source fingerprint and contain candidates.");
  }
  for (const [index, item] of annotation.cases.entries()) {
    const anchors = item.sourceAnchors ?? item.sourceAnchor;
    const normalizedAnchors = typeof anchors === "string" ? [anchors] : anchors;
    if (!Array.isArray(normalizedAnchors) || normalizedAnchors.length === 0
      || normalizedAnchors.some((anchor) => typeof anchor !== "string" || !anchor.trim())) {
      throw new Error(`Golden case ${item.caseId ?? item.id ?? index + 1} has no valid source anchors.`);
    }
    if (!Number.isInteger(item.page ?? annotation.physicalPdfPage) || (item.page ?? annotation.physicalPdfPage) < 1) {
      throw new Error(`Golden case ${item.caseId ?? item.id ?? index + 1} has no valid physical page.`);
    }
  }
}

/**
 * Compare independently verified source anchors with source citations in saved output rows.
 * This deliberately ignores model wording, audit/no-gap claims, and candidate suggestions.
 */
export function reconcileSourceObligations(annotation, output, trace = null) {
  validateInputs(annotation, output, trace);
  const outputRequirements = getSavedAnalysis(output).requirements;
  const results = annotation.cases.map((item, index) => {
    const caseId = item.caseId ?? item.id ?? `case-${index + 1}`;
    const page = item.page ?? annotation.physicalPdfPage;
    const rawAnchors = item.sourceAnchors ?? item.sourceAnchor;
    const anchors = typeof rawAnchors === "string" ? [rawAnchors] : rawAnchors;
    const anchorResults = anchors.map((anchor, anchorIndex) => {
      const normalizedAnchor = normalizeSourceText(anchor);
      const matches = outputRequirements.filter((row) => {
        const rowPage = getOutputPage(row);
        const sourceText = row?.sourceReference?.sourceText;
        const rowFingerprint = row?.sourceReference?.documentFingerprint;
        return rowPage === page
          && (rowFingerprint === undefined || rowFingerprint === annotation.sourceSha256)
          && typeof sourceText === "string"
          && normalizeSourceText(sourceText).includes(normalizedAnchor);
      });
      const traceMatches = trace?.candidates.filter((candidate) => candidate.page === page
        && candidate.sourceQuoteStatus === "matched"
        && normalizeSourceText(candidate.sourceQuote ?? "").includes(normalizedAnchor)) ?? [];
      const traceDispositions = [...new Set(traceMatches.map((candidate) => candidate.disposition))];
      const traceStatus = !trace ? "not_supplied"
        : traceDispositions.includes("accepted") ? "generated_accepted"
          : traceDispositions.includes("rejected") ? "generated_rejected"
            : traceDispositions.includes("duplicate") ? "generated_duplicate"
              : traceDispositions.includes("merged") ? "generated_merged"
                : traceDispositions.includes("discarded") ? "generated_discarded"
                  : traceDispositions.includes("incomplete") ? "generated_incomplete"
                    : "not_generated";
      return {
        anchorIndex,
        matched: matches.length > 0,
        requirementIds: [...new Set(matches.map((row) => row.id).filter((id) => typeof id === "string"))],
        traceStatus,
        candidates: traceMatches.map((candidate) => ({
          candidateId: candidate.candidateId,
          disposition: candidate.disposition,
          responsibleStage: candidate.responsibleStage,
          ...(candidate.rejectionCategory ? { rejectionCategory: candidate.rejectionCategory } : {}),
          ...(candidate.finalRequirementId ? { finalRequirementId: candidate.finalRequirementId } : {}),
        })),
      };
    });
    const matchedAnchors = anchorResults.filter((result) => result.matched).length;
    const status = matchedAnchors === anchors.length ? "source_anchors_covered"
      : matchedAnchors === 0 ? "no_source_anchor_match"
        : "partial_source_anchors";
    return { caseId, page, status, matchedAnchors, anchorCount: anchors.length, anchorResults };
  });

  const summary = results.reduce((counts, result) => {
    counts.total += 1;
    counts[result.status] += 1;
    counts.anchorsMatched += result.matchedAnchors;
    counts.anchorsTotal += result.anchorCount;
    return counts;
  }, { total: 0, source_anchors_covered: 0, partial_source_anchors: 0, no_source_anchor_match: 0, anchorsMatched: 0, anchorsTotal: 0 });

  return {
    schemaVersion: 1,
    sourceSha256: annotation.sourceSha256,
    method: "physical-page and whitespace-normalized exact substring match against requirement.sourceReference.sourceText; optional forensic candidate trace is reconciled independently",
    limitations: [
      "Measures source-anchor citation coverage only; it does not adjudicate semantic interpretation or obligation completeness.",
      "A partial source annotation is not an exhaustive recall denominator.",
      "Model audit claims such as no_gaps_reported are not used as evidence.",
      "Trace dispositions explain recorded candidates only; not_generated means no matching source-quoted candidate was recorded, not proof that a model never considered the obligation.",
    ],
    summary,
    cases: results,
  };
}

function parseArguments(args) {
  const parsed = { annotation: "", output: "", trace: "" };
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === "--annotation" && args[index + 1]) parsed.annotation = args[++index];
    else if (args[index] === "--output" && args[index + 1]) parsed.output = args[++index];
    else if (args[index] === "--trace" && args[index + 1]) parsed.trace = args[++index];
    else throw new Error("Usage: node benchmarks/scripts/evaluate-source-obligations.mjs --annotation gold.json --output saved-output.json [--trace forensic-trace.json]");
  }
  if (!parsed.annotation || !parsed.output) {
    throw new Error("Usage: node benchmarks/scripts/evaluate-source-obligations.mjs --annotation gold.json --output saved-output.json [--trace forensic-trace.json]");
  }
  return parsed;
}

async function main() {
  const args = parseArguments(process.argv.slice(2));
  const annotation = JSON.parse(await readFile(args.annotation, "utf8"));
  const output = JSON.parse(await readFile(args.output, "utf8"));
  const trace = args.trace ? JSON.parse(await readFile(args.trace, "utf8")) : null;
  process.stdout.write(`${JSON.stringify(reconcileSourceObligations(annotation, output, trace), null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : "Source-obligation evaluation failed."}\n`);
    process.exitCode = 1;
  });
}
