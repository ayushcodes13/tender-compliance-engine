# Phase 1 v2 source-region annotation protocol

**Protocol version:** 1
**Status:** active for development annotations; no annotation is a locked evaluation label by default.

## Purpose and claims

This protocol records what a reviewer can support from a specific tender source region for the bounded task of preparing a technical response matrix. It is not a tender template, a model prompt, or a claim that one annotated page represents a document family. The source document and exact byte fingerprint define the annotation target. Related copies and versions stay in the same corpus split.

Annotations distinguish requirement candidates, explicit non-requirements, ambiguous content, and unreviewed/unreadable material. “No requirement found” is an affirmative source-region judgment and must not be used for an uninspected region. Structural/parser detection is not a completeness label.

## Review unit and coverage

1. Assign each reviewed physical page and source region a stable annotation-local ID. Identify tables by table/row/cell when those parser elements are available; otherwise use a concise page-local visual description and state that the location is approximate.
2. Inventory the complete page before labeling individual obligations. Include headers, footers, headings, table labels, notes, repeated forms, and adjacent continuation context in the page coverage record, even when they are not obligations.
3. Give each region one coverage state: `complete_in_scope`, `partial`, `unreviewed`, `unreadable`, or `not_applicable`. `complete_in_scope` means every visible/selectable content unit in that named region was considered for this task; it does not mean the tender or the parser is complete.
4. Link any cross-page continuation explicitly. Review the linked page/region before claiming the obligation's complete source context. Otherwise mark the item and coverage partial.
5. Keep the annotation's document scope explicit: pages reviewed, pages in the document, region scope, and known exclusions. Never infer coverage from a count of parser-detected blocks or table rows alone.
   When `wholeDocumentReviewed` is true, every physical page must have an explicit page-level coverage record, and no region may remain `partial` or `unreviewed`. A fully inspected but unreadable region may be marked `unreadable`; this is explicit coverage, not evidence that its contents were understood. Page coverage records and region inventory are reviewer attestations, not machine proof of semantic completeness.

## Labeling obligations and non-requirements

For each independently assessable source obligation, record:

- Its source-region ID and one or more literal source anchors. Keep quotes short enough to identify the evidence and long enough to preserve the operative subject, action, qualifiers, and condition. Do not paraphrase inside a quotation.
- An interpretation summary, separated from the source quote and clearly marked as reviewer wording.
- A task disposition: technical, service/fulfilment, documentation/deliverable, administrative/form, explicit non-requirement, ambiguous, or unresolved. The task determines relevance; do not silently discard content because it is unfamiliar.
- Atomicity: `independent` when it can be answered/reviewed separately; `grouped` with a shared group ID when the source makes the obligations inseparable; or `undetermined` when the boundary needs adjudication. Do not merge separate bullets merely because they share a table row.
- Source modality and actors as written (`must`, `shall`, `should`, `may`, negation, named actor). Do not normalize a recommendation into a mandatory condition.
- Every stated value, unit, operator, duration, range, threshold, count, and qualifier as a literal raw token. Preserve signs and inequality direction. A normalized interpretation may be added only in a separate field and must not replace the raw token.
- Conditions, exceptions, alternatives, temporal start/end points, and scope qualifiers. Keep ambiguous attachment/scope visible instead of choosing an interpretation.
- Uncertainty reasons such as OCR ambiguity, conflicting clauses, unclear actor, unreadable content, duplicate wording, or uncertain task relevance. “None” is permitted only after the region has been reviewed.

For content that is not an obligation for this task, record the source region and why it is excluded (for example: page number, column header, or explanatory example). Distinguish structural labels from a substantive instruction. If content could be a bidder document or an operational deliverable, label it accordingly or ambiguous; do not call it irrelevant merely because it is not a device specification.

## Source and location fidelity

- Store the source file SHA-256, physical PDF page, and printed page label separately when present.
- Store source quotes exactly as seen in the source. If a verifier uses whitespace-normalized matching, record that method; do not change token spelling, digits, units, operators, or word order.
- Record parser element IDs, offsets, and bounding boxes only when obtained from the named parser/version and verified against the page. Include offset unit/scope and coordinate system. Unknown is `null`/omitted, never a guessed value.
- Separate quote fidelity from location precision. A literal quote may be verified on a page even when its exact table cell or geometry is unknown; label that location `page_only` or `approximate`, not `exact`.
- For OCR/visual transcription, preserve the transcript and method separately from the visual source. Keep confidence and unresolved glyphs; never silently correct OCR.
- Do not put full extracted pages, model prompts/responses, credentials, or unrelated personal data in committed annotations. Store only the minimum source anchors needed for audit. Keep source PDFs and private analysis artifacts in access-controlled local storage.

## Adjudication and disagreement

Every record carries an annotation status:

- `draft`: initial labels have not been independently checked.
- `reviewed_pending_adjudication`: one reviewer has checked the cited source; independent review or disagreement resolution is outstanding.
- `adjudicated`: a second reviewer has checked the source and labels; disagreements are recorded with both positions and a resolution rationale.
- `unresolved`: evidence or interpretation remains disputed; this item cannot be treated as a single gold answer.

Record reviewer role/identifier, date, reviewed pages/regions, and any source-backed corrections. A second reviewer must not see model output when producing expected labels if the labels will evaluate that output. During adjudication, preserve the initial labels and record what changed. No disagreement observed by one reviewer is not evidence of independent agreement.

The sample annotation in this directory is a provisional, assistant-assisted page review. It is **development material**, not adjudicated gold and not an evaluation result. Its one-page scope is intentionally partial at tender level.

## Before scoring a pipeline

1. Verify the source fingerprint and every quoted anchor against the specified physical page.
2. Confirm page/region coverage and unresolved items; a source anchor alone does not prove exhaustive annotation.
3. Resolve obligation atomicity and task disposition disagreements, or retain the region as unresolved.
4. Ensure labels were prepared independently of the output being scored. If a document influenced a prompt, code, route, or threshold, keep it in development.
5. Report annotation status, document/page sample size, modality/layout limitations, and unreviewed coverage beside any metric.

## Minimal acceptance for this protocol milestone

- New records validate against the versioned schema and consistency checks.
- The source hash and all quotes are verified against the source PDF/page without copying full page text to the output.
- The annotation records both obligations and non-requirements and covers its declared page scope.
- Atomicity, literal values/units/operators, source modality/conditions, uncertainty, and adjudication state are explicit.
- Partial document coverage and unresolved or unadjudicated judgments remain explicit; no output is called gold until adjudication is complete.
