# Evaluation Strategy

Quality must be measured against a curated benchmark, not judged from demos.

## Phase 1 metrics

### Requirement extraction

- requirement-level precision
- requirement-level recall
- split accuracy
- merge/grouping accuracy
- duplicate rate
- invented-requirement rate

### Provenance

- page citation accuracy
- clause/section accuracy
- source-text fidelity
- exact/approximate location correctness
- bounding-box correctness where available

### Normalization

- numeric value fidelity
- unit fidelity
- operator fidelity
- range-bound fidelity
- false normalization rate
- correct human-review escalation rate

### OCR

- OCR-warning precision/recall
- source preservation under OCR corruption
- rate of silent meaning-changing correction (target: zero)

## Benchmark cases

Dataset should deliberately include:

- minimum/maximum/exact values
- ranges and tolerances
- percentages
- unit-bearing requirements
- multi-line tables
- numbered and nested clauses
- multiple requirements in one sentence
- requirements spanning multiple sentences/pages
- repeated headers/footers
- scanned pages
- OCR symbol corruption (`≥`, `≤`, `µ`, decimal separators)
- ambiguous terminology
- duplicate requirements
- missing/uncertain page coordinates

## Later Phase 2 metrics

- evidence retrieval precision/recall
- numeric comparison accuracy
- unit-conversion accuracy
- compliance classification accuracy
- citation correctness
- contradiction-detection recall
- hallucination rate
- false non-compliance rate
- **false compliance rate**

False compliance should carry the highest release-severity weighting.

## Evaluation record

Every benchmark example should contain:

- immutable source document/version
- gold source page/region
- gold requirement text
- expected split/grouping
- gold normalization where safe
- expected review/escalation state
- annotator notes

Model/provider/prompt/parser versions must be recorded with each evaluation run.
