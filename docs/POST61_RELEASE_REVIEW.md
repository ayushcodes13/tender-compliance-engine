# Post-CP61 release review and manual acceptance checklist

## What this hardening pass proved

The product is no longer validated only through database-seeded checkpoint tests.

Automated coverage now includes:

1. project and tenant/auth lifecycle;
2. tender HTTP upload → immutable storage metadata → queue → worker → parsed source pages;
3. OEM HTTP upload → queue → worker → immutable OEM version → searchable page-scoped OEM text segments;
4. requirement extraction/normalization/review service behavior;
5. evidence retrieval and human curation;
6. deterministic unit/specification comparison;
7. conservative qualitative reasoning and conflict detection;
8. missing-evidence clarification/deviation workflows;
9. human assessment confirmation/override/reopen/audit;
10. final matrix projection;
11. XLSX, DOCX, and PDF generation/download metadata;
12. submission create → lock → approve → revoke lifecycle;
13. Phase 1 critical extraction/citation gates and Phase 2 zero-false-compliance gate;
14. cross-tenant security tests and hostile-upload/adversarial parser tests;
15. API, worker, and web production Docker builds.

## Adversarial findings fixed after CP61

### 1. OEM uploads could not reach evidence retrieval

**Finding:** the OEM upload route queued an `OemDocumentVersion.id`, while the worker only resolved tender `DocumentVersion` IDs.

**Impact:** a normal user could upload an OEM datasheet in the browser, but it could not become searchable evidence without manually seeded database rows.

**Fix:** PR #76 teaches the worker to process OEM versions and adds upload-driven regression coverage.

### 2. Untrusted tender text was inserted as raw HTML

**Finding:** the source viewer used `dangerouslySetInnerHTML` to display `page.cleaned_text`.

**Impact:** uploaded/derived document text is untrusted. Raw HTML insertion created a stored-XSS surface in the text-only source fallback.

**Fix:** render the text through normal React escaping while preserving line breaks with the existing `white-space: pre-wrap` CSS. CI now rejects any future `dangerouslySetInnerHTML` usage in the application UI.

### 3. Worker comments no longer described reality

**Finding:** worker documentation still said OCR/CLEANUP/EXTRACT were placeholders even though OCR and extraction are implemented and cleanup is applied during page persistence.

**Impact:** this was not a runtime bug, but it made code review and operational debugging misleading.

**Fix:** documentation now states the real stage behavior and explains why CLEANUP is an explicit audit stage whose deterministic transformation is applied atomically inside page persistence.

## What is intentionally not proven by CI

CI gives strong integration coverage, but it is not a substitute for a human acceptance run in the deployed UI.

The following still require a product-owner/manual pass:

- real browser interaction rather than TypeScript/build-only frontend verification;
- a representative real tender PDF from your target market;
- a genuinely scanned/low-quality tender that exercises installed Tesseract/OCR;
- a representative OEM datasheet/manual with tables and technical units;
- visual correctness of page images, source highlights, scrolling, zoom, and responsive layout;
- quality of requirement splitting/grouping on the exact tender style you care about;
- quality of evidence retrieval on real OEM wording;
- correctness of final XLSX/DOCX/PDF formatting for the submission style you intend to send to customers;
- production identity-provider setup (development header auth is only a development path);
- production object storage, Redis, database, malware scanner, secrets, backups, and retention configuration;
- real external LLM-provider behavior/cost/latency when that adapter is enabled.

## Exact manual acceptance run

Use one real tender and one real OEM source. Do not start with a synthetic happy-path document.

### A. Project and tender ingestion

- [ ] Open the application as a normal user.
- [ ] Create a new tender project.
- [ ] Upload a normal digital tender PDF.
- [ ] Confirm the browser shows the uploaded filename/version and a truthful processing state.
- [ ] Confirm processing reaches a terminal state without manually touching the database.
- [ ] Open at least five extracted requirements from different pages/sections.
- [ ] For each, verify the displayed source page and quoted text against the original PDF.
- [ ] Confirm an unknown clause/location remains unknown rather than being invented.

### B. OCR / difficult source

- [ ] Upload a scanned or mixed scanned/digital tender.
- [ ] Verify OCR is used only where needed.
- [ ] Check at least five meaning-sensitive values: decimals, ≥/≤, µ/μ, percentages, tolerances, and units.
- [ ] Confirm uncertain OCR appears as warning/review-needed rather than silently corrected.

### C. Requirement review

- [ ] Edit normalized wording and refresh; verify persistence and revision history.
- [ ] Split one requirement and verify both children retain correct source provenance.
- [ ] Merge two appropriate requirements and verify all contributing sources remain visible.
- [ ] Reorder/categorize/add notes/mark mandatory where supported.
- [ ] Mark reviewed, reopen, and escalate a requirement; verify counts/timeline update.

### D. OEM/vendor source

- [ ] Upload a real OEM datasheet/manual from the browser.
- [ ] Confirm it processes without database seeding.
- [ ] Verify the OEM document/version appears after refresh.
- [ ] Propose evidence for several requirements.
- [ ] Open each proposed evidence item in source context before accepting it.
- [ ] Reject at least one plausible-but-wrong candidate.

### E. Comparison adversarial cases

Manually verify these cases because they represent the highest-risk false-compliance failures:

- [ ] **Same number, wrong metric:** tender asks for resolution; OEM source states accuracy with the same number. Must not become COMPLIANT.
- [ ] **Wrong entity/model:** correct value appears for another product/model. Must not become COMPLIANT.
- [ ] **Wrong condition/scope:** value is valid only under a different operating condition. Must escalate/mismatch appropriately.
- [ ] **Compatible unit conversion:** e.g. equivalent mm/µm values compare correctly and the conversion is explainable.
- [ ] **Boundary case:** exact equality at a ≥ or ≤ threshold behaves correctly.
- [ ] **Missing evidence:** must remain NOT_DEMONSTRATED/HUMAN_REVIEW_REQUIRED, never NON_COMPLIANT solely because retrieval found nothing.
- [ ] **Contradictory OEM sources:** both sources remain visible and the requirement enters CONFLICT rather than silently choosing one.

### F. Human compliance review

- [ ] Run an assessment.
- [ ] Confirm one system assessment without changes.
- [ ] Override one assessment with a required reason.
- [ ] Reopen it and verify the action is auditable.
- [ ] Add a reviewer comment.
- [ ] Resolve one conflict explicitly.
- [ ] Generate/edit/answer a clarification.
- [ ] Propose and accept/reject a deviation.

### G. Final deliverables

- [ ] Open the final compliance matrix and confirm unresolved rows are still visible.
- [ ] Compare at least ten matrix rows against tender source, accepted OEM evidence, and the shown status.
- [ ] Generate XLSX, DOCX, and PDF.
- [ ] Open all three files locally.
- [ ] Check filenames/MIME behavior, ordering, wrapping, source references, statuses, deviations, and clarifications.
- [ ] Confirm no export wording implies compliance for an unresolved row.

### H. Submission lifecycle

- [ ] Create a submission version.
- [ ] Lock it.
- [ ] Attempt to change the locked snapshot through the supported UI/API; it must remain immutable.
- [ ] Approve it and verify approver/time metadata.
- [ ] Make a later project change and confirm it does not rewrite the approved version.
- [ ] Create a new submission version for the changed state.
- [ ] Revoke an approved submission and verify history remains available.

## Release decision

Call the product ready only when:

- CI is green on the release commit;
- the manual acceptance run above is completed on representative documents;
- every false-compliance adversarial case behaves conservatively;
- source navigation is visually trustworthy;
- final exported artifacts are acceptable to the intended tender-response user;
- production auth/storage/queue/database/scanner/backup settings are configured rather than using development/fake defaults.

The remaining manual work is deliberate human acceptance, not another hidden product subsystem.
