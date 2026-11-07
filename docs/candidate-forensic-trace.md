# Opt-in local candidate trace

For a local analysis, start the app with `TCE_FORENSIC_TRACE=1`. On a non-hosted run, each analysis writes one JSON file under `apps/web/.local/forensic-traces/`. The directory is created with mode `0700`, trace files with mode `0600`, and `.local/` is Git-ignored. Hosted deployments ignore the setting. Trace write failures produce a generic warning and do not alter the analysis result.

The trace keeps the original parser text in `sourceQuote` and the model proposal in `modelQuote`. `sourceQuoteStatus: "unavailable"` means no exact native/OCR/table quote could be recovered; the model wording is not substituted as source evidence. Records carry the source document fingerprint, page, parser element IDs, source row/cell indices when present, stable candidate IDs, origin, terminal disposition, responsible stage/category, and final requirement ID when accepted. Current dispositions include accepted, rejected, duplicate, merged, discarded, or incomplete. There is no merge step in the current candidate-validation path; the field is available to represent a later explicit merge.

The trace is observational: it runs after extraction candidates exist, reads no model credentials, changes no prompts, and does not feed back into candidate filtering or validation. Exact tender text is written only to the opt-in protected local trace; normal application logs receive no candidate text.

## Diagnosing the IIT Guwahati page-11 misses

Run the tender locally with tracing enabled, then compare the candidate records on physical page 11 with the source anchors in `benchmarks/representative-tenders/heldout-golden-v0.6.json`. Convert each source anchor into an `ExpectedSourceUnit` input for `compareExpectedSourceUnits` in `apps/web/app/candidate-trace.ts` and inspect its status plus the listed candidate IDs:

- `not_generated`: no candidate record points to the annotated source wording/element.
- `generated_rejected`: at least one candidate points to the obligation source, but validation ended it in rejection.
- `generated_accepted`: the candidate survived with a final requirement ID; inspect that requirement's model wording for partial coverage.

The v0.6 page-11 annotations are assistant-reviewed source anchors with human adjudication pending, so this comparison is diagnostic evidence, not an exhaustive recall score. For the five-year AMC, local India after-sales presence, and beyond-warranty spare-parts support, the trace will show whether initial extraction or either omission audit produced a candidate, and whether routing, source validation, or containment removed it. It cannot reconstruct the missing text from the prior 47 aggregate omission count.

`docs/candidate-forensic-trace.synthetic.json` demonstrates accepted, rejected, duplicate, never-generated, and generated-rejected cases without real tender content.
