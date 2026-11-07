import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { CandidateTraceLedger, compareExpectedSourceUnits, resolveForensicTraceConfig, writeForensicTrace } from "./candidate-trace.ts";
import { keepParsedSourceCandidate } from "./visual-table.ts";

const sourceQuote = "Provide after-sales service and spare parts for five years.";

test("assigns stable IDs and terminal dispositions for extraction and both recovery audits", () => {
  const ledger = new CandidateTraceLedger("fingerprint-1");
  const sourceElementIds = ["page-11:cell-3"];
  const source = ledger.register({ page: 11, origin: "vector_table_extraction", modelQuote: sourceQuote, sourceQuote, sourceQuoteStatus: "matched", sourceElementIds, sourceRowIndex: 2, sourceColumnIndex: 1 });
  const recovered = ledger.register({ page: 11, origin: "source_row_recovery", modelQuote: "five years of spare-parts support", sourceQuote, sourceQuoteStatus: "matched", sourceElementIds, sourceRowIndex: 2, sourceColumnIndex: 1 });
  const audited = ledger.register({ page: 11, origin: "text_page_omission_audit", modelQuote: sourceQuote, sourceQuote, sourceQuoteStatus: "matched", sourceElementIds });
  ledger.terminate(source, { disposition: "accepted", responsibleStage: "candidate_validation", finalRequirementId: "req-3" });
  ledger.terminate(recovered, { disposition: "rejected", responsibleStage: "source_quote_validation", rejectionCategory: "source_quote_or_location_not_verified" });
  ledger.terminate(audited, { disposition: "duplicate", responsibleStage: "omission_containment", rejectionCategory: "already_covered_by_existing_candidate", relatedCandidateId: source });

  const secondRun = new CandidateTraceLedger("fingerprint-1");
  const stable = secondRun.register({ page: 11, origin: "vector_table_extraction", modelQuote: sourceQuote, sourceQuote, sourceQuoteStatus: "matched", sourceElementIds, sourceRowIndex: 2, sourceColumnIndex: 1 });
  assert.equal(source, stable);
  assert.equal(ledger.summary().total, 3);
  assert.equal(ledger.summary().accepted + ledger.summary().rejected + ledger.summary().duplicate + ledger.summary().merged + ledger.summary().discarded + ledger.summary().incomplete, 3);
  assert.equal(ledger.records.find((row) => row.candidateId === source).finalRequirementId, "req-3");
  assert.deepEqual(ledger.records.find((row) => row.candidateId === source).sourceElementIds, sourceElementIds);
});

test("reconciles terminal dispositions across every candidate origin", () => {
  const ledger = new CandidateTraceLedger("fingerprint-origins");
  const origins = ["initial_extraction", "vector_table_extraction", "source_row_recovery", "text_page_omission_audit", "visual_page_omission_audit"];
  const dispositions = ["accepted", "rejected", "duplicate", "merged", "discarded"];
  for (const [index, origin] of origins.entries()) {
    const id = ledger.register({ page: index + 1, origin, modelQuote: `candidate ${index}`, sourceQuote: `source ${index}`, sourceQuoteStatus: "matched", candidateOrdinal: index });
    ledger.terminate(id, { disposition: dispositions[index], responsibleStage: `fixture_stage_${index}` });
  }
  const records = ledger.finalize();
  assert.equal(records.length, origins.length);
  assert.ok(records.every((record) => record.disposition !== "incomplete"));
  const counts = ledger.summary();
  assert.equal(counts.accepted + counts.rejected + counts.duplicate + counts.merged + counts.discarded + counts.incomplete, counts.total);
});

test("expected source units distinguish never generated from generated and rejected", () => {
  const ledger = new CandidateTraceLedger("fingerprint-1");
  const rejectedId = ledger.register({ page: 11, origin: "initial_extraction", modelQuote: "A different generated sentence", sourceQuote, sourceQuoteStatus: "matched", sourceElementIds: ["p11-amc"] });
  ledger.terminate(rejectedId, { disposition: "rejected", responsibleStage: "candidate_validation", rejectionCategory: "invalid_candidate_text" });
  const acceptedId = ledger.register({ page: 11, origin: "source_row_recovery", modelQuote: sourceQuote, sourceQuote, sourceQuoteStatus: "matched", sourceElementIds: ["p11-parts"] });
  ledger.terminate(acceptedId, { disposition: "accepted", responsibleStage: "candidate_validation", finalRequirementId: "req-8" });
  const results = compareExpectedSourceUnits([
    { expectedUnitId: "amc", page: 11, sourceQuote: "Provide after-sales service and spare parts for five years.", sourceElementIds: ["p11-amc"] },
    { expectedUnitId: "local-support", page: 11, sourceQuote: "Maintain a local office or authorized associate in India.", sourceElementIds: ["p11-local"] },
  ], ledger.finalize());
  assert.deepEqual(results.map((row) => row.status), ["generated_rejected", "not_generated"]);
});

test("enabling trace bookkeeping leaves candidate validation outcomes unchanged", () => {
  const candidates = [
    { quote: "A standalone obligation.", row_type: "requirement" },
    { quote: "Standalone", row_type: "requirement" },
  ];
  const baseline = candidates.filter((candidate) => keepParsedSourceCandidate(candidate, candidates.map((row) => row.quote)));
  const ledger = new CandidateTraceLedger("fingerprint-2");
  const traced = candidates.map((candidate) => ({
    candidate,
    id: ledger.register({ page: 1, origin: "initial_extraction", modelQuote: candidate.quote, sourceQuote: candidate.quote, sourceQuoteStatus: "matched" }),
  }));
  const withTrace = traced.filter(({ candidate }) => keepParsedSourceCandidate(candidate, candidates.map((row) => row.quote)));
  assert.deepEqual(withTrace.map(({ candidate }) => candidate), baseline);
  assert.equal(ledger.summary().total, 2);
});

test("forensic trace is opt-in and disabled on hosted deployments", () => {
  assert.deepEqual(resolveForensicTraceConfig({}), { enabled: false, directory: null });
  assert.equal(resolveForensicTraceConfig({ TCE_FORENSIC_TRACE: "1", VERCEL: "1" }).enabled, false);
  const local = resolveForensicTraceConfig({ TCE_FORENSIC_TRACE: "1" });
  assert.equal(local.enabled, true);
  assert.match(local.directory, /\.local[\/]forensic-traces$/);
});

test("writes source-bearing traces with restrictive local file permissions", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "tce-forensic-"));
  try {
    const ledger = new CandidateTraceLedger("fingerprint-protected");
    const id = ledger.register({ page: 1, origin: "initial_extraction", modelQuote: "Model wording", sourceQuote: "Original PDF wording", sourceQuoteStatus: "matched" });
    ledger.terminate(id, { disposition: "rejected", responsibleStage: "fixture", rejectionCategory: "fixture_rejection" });
    const target = await writeForensicTrace(directory, { documentFingerprint: "fingerprint-protected", candidates: ledger.finalize() });
    const dir = await stat(directory);
    const file = await stat(target);
    const trace = JSON.parse(await readFile(target, "utf8"));
    assert.equal(file.mode & 0o777, 0o600);
    assert.equal(dir.mode & 0o777, 0o700);
    assert.equal(trace.candidates[0].sourceQuote, "Original PDF wording");
    assert.equal(trace.candidates[0].modelQuote, "Model wording");
    assert.equal(trace.summary.rejected, 1);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
