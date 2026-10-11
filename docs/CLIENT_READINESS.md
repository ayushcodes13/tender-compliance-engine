# Client readiness for the tender response sheet

## Product promise

The client-facing pilot takes a tender PDF or DOCX, extracts and organizes the
technical specifications in the tender's technical-specification section or
clearly identifiable specification tables, preserves their source links, and
exports a response sheet with blank fields for the OEM to complete. It does
not invent specifications or decide whether an OEM complies.

## Release gates

Complete these in order. A passing automated test does not replace the live
document review in steps 3–5.

### 1. Prepare the private pilot environment

- [ ] Rotate and privately configure the model-provider key. Do not put it in a
  commit, screenshot, chat message, or shared log.
- [ ] Start the bundled production-mode pilot from the release commit.
- [ ] Confirm `/api/backend/ready` reports the database, queue, worker, durable
  storage, malware scanner, and model provider as production-ready.
- [ ] Confirm the web app, API, and worker all run the same release version.
- [ ] Keep access on localhost or behind a trusted private network/VPN. The
  single-workspace pilot has no application sign-in and must not be exposed
  directly to the public internet.

### 2. Resolve the three supplied examples

- [ ] For Examples 1, 2, and 3, inspect every technical row and nested item
  against the tender page and the supplied response-sheet example.
- [ ] Preserve wording, values, symbols, units, section numbering, and nested
  row structure. Record differences as review findings; do not silently repair
  the tender wording.
- [ ] Classify every surfaced potential omission against the selected tender
  section. Resolve confirmed technical rows and record a reason for findings
  that do not belong in the response sheet.
- [ ] Resolve failed or uncovered source windows, or keep the export explicitly
  marked for human review.
- [ ] Do not claim tender-wide completeness while any relevant finding or
  window remains unresolved.

### 3. Verify scanned and meaning-sensitive text

- [ ] Upload a scanned or mixed-quality tender using the production worker.
- [ ] Check at least five values or symbols where OCR errors can change meaning,
  such as decimals, `≥`/`≤`, `µ`/`μ`, percentages, tolerances, and units.
- [ ] Confirm uncertain recognition stays in an OCR/review state until a person
  checks the rendered source page.

### 4. Run the customer browser flow

- [ ] Create a project and upload a representative client tender without manual
  database edits.
- [ ] Wait for a truthful terminal processing state and inspect at least five
  rows from different pages or sections.
- [ ] Open each cited page and verify the exact source wording, values, and
  location shown in the review UI.
- [ ] Confirm the response contains only the selected tender technical section
  or specification tables, with parent and nested items organized for the OEM.
- [ ] Export the DOCX response sheet, open it in a document viewer, and verify
  row order, wrapping, page breaks, blank OEM fields, and source wording.
- [ ] Confirm review-required validation or coverage findings remain visible
  and are not presented as a completeness guarantee.

### 5. Confirm operating commitments with the pilot customer

- [ ] Agree that a reviewer checks the sheet before sending it to the OEM.
- [ ] Confirm the configured model provider and customer-data terms are
  acceptable for the tender documents being uploaded.
- [ ] Agree on who can access the private pilot, how originals/exports are
  retained, and how backups and restoration are handled.
- [ ] Provide a support contact and a process for reporting incorrect rows,
  missing specifications, and source-navigation problems.

### 6. Verify release checks

- [ ] Run the required GitHub Actions workflows on the release commit once
  repository billing permits them to start.
- [ ] Record the release commit, acceptance documents, unresolved limitations,
  and the customer's sign-off before calling the pilot accepted.

## Evidence recorded for the current code

On 2026-10-12, a clean checkout of `main` at `fa25088` passed the API suite
(1,347 passed, 2 skipped), web typecheck, production build, and all 17 browser
E2E tests. These checks establish code-level behavior only. They do not complete
the sample classification, live provider/OCR acceptance, customer deployment,
or GitHub Actions release gates above.
