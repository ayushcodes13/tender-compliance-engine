# Independent End-to-End Acceptance Audit — 2026-11-09

## Recommendation

**NO-GO for a supervised customer pilot.** The hosted application is unavailable because production access control is unconfigured. The locally tested workflow also lost operator edits after refresh, opened the wrong source page from a citation, admitted bidder and contract language into the technical response sheet, failed on two large tenders, and could not export one tested sheet to PDF because of source characters.

This report records acceptance evidence and a bounded backlog. It does not change application behavior or claim that the test corpus is a statistically representative accuracy benchmark.

## Tested revisions and environment

- **Live analysis application code:** `6f215abe9757034ef9a0eb1676a7f1b254b46ab8` (`fix/bound-analyze-upload-body`). This is the code revision used for the three user-provided tender runs and the NIOT tender run.
- **Current checkout at report time:** `2819004518d5954cf5e59460d168459ab22b427f`. Its only change after the live-analysis revision is `apps/web/scripts/verify-pipeline.mjs`; no application runtime file changed. The automated checks below ran on this current checkout.
- **Base:** `origin/main` at `2d7f89e134c288ef94035402f389a155cc40a43b` when fetched on 2026-11-09.
- **Runtime:** local Next.js app on loopback, using the configured GPT-6 Luna provider credentials from the ignored local environment file. No key, endpoint secret, or credential value is included here.
- **Hosted app:** `https://tender-compliance-engine.vercel.app/`, requested on 2026-11-09. It returned HTTP 503 with the response body `Application access is not configured. Set APP_ACCESS_PASSWORD before serving production traffic.`
- **Data handling:** user PDFs and model SSE responses remain local and are not included in this report PR. Provider usage/cost fields were absent from the completed saved analysis objects; no token or cost numbers are claimed.

## Automated checks

Commands run from `apps/web` on `2819004518d5954cf5e59460d168459ab22b427f`:

| Command | Result | Evidence boundary |
| --- | --- | --- |
| `npm test` | **370 passed, 0 failed** | Unit and benchmark-script tests; synthetic and mocked tests are not live tender accuracy evidence. |
| `npm run typecheck` | **Passed** | TypeScript compilation only. |
| `npm run build` | **Passed** | Optimized Next.js production build. |
| `npm run test:pipeline` | **Passed, 26/26 cases** | Scripted contract only; verifier reports `realTenderQualityScore: null`, 24 route calls and 31 extraction calls. |

The pipeline command was first attempted while a dev server had replaced the production `.next` build; it exited because the production build ID was missing. After stopping the dev server, rebuilding, and rerunning the same command, all 26 scripted cases passed. This first failure was a test-environment setup issue, not a pipeline assertion failure.

## Test corpus and provenance

The first three PDFs and DOCX files are user-provided fixture pairs present under `examples/`. Their original publishing URLs and public/confidential status were not established in this audit. Their DOCX files are comparison targets supplied by the user, not independently adjudicated gold labels.

| Source PDF | Pages | Bytes | SHA-256 | Origin / outcome |
| --- | ---: | ---: | --- | --- |
| `examples/input 1.pdf` | 18 | 353,497 | `7e381ceb3acbc7b08abe1c958cd793972ce89831d94d1586f9a84eab55640d2f` | User-provided; analysis completed. Compared with supplied `output 1.docx` (38,004 bytes; SHA-256 `c194d3fc989cdd7936d49a162ef17e1647dbbf6a7c729df3862c99566a4b8809`). |
| `examples/input 2.pdf` | 37 | 824,675 | `e2eac72281a707a8855646f70acbd5a35e5ff680ecb0b25cb48375f990780b7d` | User-provided; analysis timed out without a sheet. Supplied target `output 2.docx` (400,640 bytes; SHA-256 `f73c3c4c2455ef1a3edee8f0904edfc35b84b1378b296d4aabc66209eaa2dea3`) could not be compared to a new result. |
| `examples/input 3.pdf` | 41 | 2,153,673 | `607966f4e1957c9921216734fce3d69c1dc6ea19d9979a45f217cbd0c2c1777e` | User-provided; routing failed before extraction. Supplied target `output 3.docx` (679,191 bytes; SHA-256 `9391a242074877b374046aa5f3cea8283c9219b223eb81da8487887e1f7acee1`) could not be compared to a new result. |
| `examples/NIOT Chennai - Auto Salinometer.pdf` | 25 | 1,598,894 | `29838bdb3001addc4c4c970f279f802d070ffc1bcb253a11504715206ec644a0` | Public real tender. Tender number `NIOT/S&P/OH/50015/2026-27`, issue date 2026-11-06, and title match the official [Government eProcurement listing](https://eprocure.gov.in/eprocure/app?id=LatestDynamicTenderList&page=FrontEndViewTender&service=page&sp=S5HVE7MOWk3HH6YbeNSvmpA%3D%3D). Analysis completed. |

The 18-page file is the small case in this sample, NIOT is the medium case, and the 37- and 41-page files are the large cases. These size labels describe this test set, not general page-count limits.

## Live analysis outcomes

| Tender | HTTP / time | Result | Direct observations |
| --- | --- | --- | --- |
| Input 1, 18 pages | 200 / **102.651 s** | Completed. UI showed **39 response rows**, **51 held candidates**, **90 pending review**, and **0/39 checked by the operator**. | The response sheet included bid-format and bidder/contract language. On source PDF p.10, the target DOCX contains the “III-V compatible tips” requirement under Diamond tips, while the model result omitted that subpointer. Several technical subpoints were grouped in a row instead of one separately assessable subpointer per row. |
| Input 2, 37 pages | 200 / **290.035 s** | Failed explicitly: `Analysis time limit reached. Processing is incomplete; no response sheet was produced.` | Progress reached page reading 37/37 and table layout mapping 19/19, then timed out at 18/20 table audits. No output-quality comparison is possible. |
| Input 3, 41 pages | 200 / **87.921 s** | Failed explicitly: `The configured model could not route PDF page group 4. No extraction was attempted.` | Page reading had reached 23/41 and local OCR ran for one page, but extraction did not start and no sheet was produced. No output-quality comparison is possible. |
| NIOT Auto Salinometer, 25 pages | 200 / **119.924 s** | Completed. Analysis returned **77 requirement entries** and **18 section entries**. | The source pages 18 and 20 both contain the same 14-item technical specification schedule. The analysis represented 12 repeated specification items as requirement rows on both pages; make/model lines were represented as section entries. Visual review of those pages found the displayed numeric values consistent between the two copies; this is not a full numeric audit of every row. The analysis also returned 19 requirement entries from outside the technical annexure pages 18 and 20–22, including bidder-facing, contract, and declaration material that requires screening before a technical response sheet is usable. |

For input 1, the UI correctly showed an incomplete-draft alert, 13 pages with possible omissions, 12 router-uncertain pages, 2 unmapped table rows, and 18 clipped router pages. It did **not** silently present full-document coverage as complete. The warning is useful, but the volume of held items and the accepted scope contamination leave substantial operator work.

## Manual and synthetic workflow checks

### Source navigation and citation review

Using input 1’s saved analysis stream replayed into the current UI with the original PDF loaded (no additional provider call), clicking the response-row citation labeled `page 10` opened the source panel at **Page 6**. The panel said no requirement was selected and no quote was highlighted. Expected behavior is to open PDF page 10 with the cited passage selected/highlighted. This was reproduced with the exact row citation button. The source document and API result were the same; the defect is in the review navigation/highlight path or its page mapping.

### Editing and exports

Using the same real-PDF UI replay, a description was edited and another row removed:

- **DOCX:** downloaded and parsed. The edited description was present; the removed row was absent; a source-page citation remained.
- **XLSX:** downloaded and parsed with ExcelJS. The edited description was present; the removed row was absent. The workbook had 66 physical rows, including blank/section/header rows; the UI showed 38 response entries after the removal.
- **PDF:** no PDF download was emitted. The app displayed: `The PDF font cannot render one or more source characters. Download DOCX or Excel to preserve the wording.` The tested sheet therefore could not be exported to PDF, although DOCX/XLSX preserved the edit. No claim is made about PDF export for every possible tender.

### Refresh and cancellation

- **Refresh:** after editing the input 1 response sheet, a browser reload returned to the upload screen; the selected PDF and correction were gone. The app’s checkpoint documents that state is held in browser memory, but the UI did not protect unsaved operator work or offer recovery. Repro: upload/restore an analysis, edit `Description, row 1`, reload.
- **Cancellation (synthetic UI harness):** a pending `/api/analyze` request was held by a stub and cancelled through the visible `Cancel processing` button. UI state changed to `Processing cancelled after 0s. The selected PDF is ready to try again.` No provider call was made.
- **Upload rejection (synthetic file):** a 33 MiB local upload returned HTTP 413 with a size-limit error. A small malformed `%PDF` file returned an explicit invalid-PDF error and no analysis sheet.

## Risk-ranked findings

### P0 — Hosted production is unavailable

- **Reproduce:** request `https://tender-compliance-engine.vercel.app/` on 2026-11-09.
- **Expected:** the configured production app responds with the upload/review interface.
- **Observed:** HTTP 503. Response body states that `APP_ACCESS_PASSWORD` is not configured.
- **Suspected root cause:** the production environment lacks the required application access password. This is directly indicated by the middleware response; deployment configuration was not changed or inspected in the Vercel dashboard during this audit.

### P0 — Refresh discards operator corrections without recovery

- **Reproduce:** use input 1, change `Description, row 1`, then reload before downloading.
- **Expected:** preserve the working review, warn before discarding it, or provide a recovery path for the corrected sheet.
- **Observed:** the app returned to the initial upload form; the edit and selected document were gone.
- **Suspected root cause:** analysis and edits exist only in React/browser memory; there is no draft persistence or unsaved-change guard.

### P1 — Large documents do not reach a response sheet

- **Reproduce:** analyze the supplied 37-page input 2 or 41-page input 3 with the tested local provider configuration.
- **Expected:** produce a bounded, reviewable sheet or an actionable failure that lets the operator resume/retry the incomplete stage.
- **Observed:** input 2 timed out after 290.035 seconds during table audits; input 3 stopped before extraction because routing page group 4 failed. Both returned no sheet.
- **Suspected root cause:** synchronous end-to-end deadlines and all-or-nothing routing/extraction; a single page-group provider failure aborts the 41-page workflow.

### P1 — Citation button opens the wrong source page

- **Reproduce:** in the input 1 response sheet replay, click a citation labeled page 10.
- **Expected:** show PDF p.10 and the selected evidence quote/highlight.
- **Observed:** drawer title was Page 6 source and the drawer reported no selected requirement or highlight.
- **Suspected root cause:** response-row/source-page state mapping in the client source viewer. A browser replay reproduced the client interaction, but the navigation issue should be rechecked against a non-replayed live session before attributing it solely to the web client.

### P1 — Bidder instructions and contract language enter the technical sheet

- **Reproduce:** analyze input 1 or the public NIOT tender and inspect response rows against their visual source pages.
- **Expected:** keep product/system specifications and relevant technical supply requirements in the technical requirement matrix; separate bidder instructions, evaluation provisions, commercial clauses, and declarations from that matrix.
- **Observed:** input 1 produced rows for tender response-format and bidder/contract language. NIOT analysis included 19 requirement entries on pages outside Annexure I’s technical specification pages; visual inspection found bidder-facing and contract/declaration material among them.
- **Suspected root cause:** classification and scope normalization admit clauses from general tender sections as technical requirements. Some after-sales, training, or delivery obligations may be relevant and require human judgment; the count is a review workload, not a claim that every one of the 19 rows is invalid.

### P1 — PDF export refuses the tested source characters

- **Reproduce:** from the input 1 edited response sheet, click `Download PDF`.
- **Expected:** produce a PDF containing the edited sheet, or identify an actionable conversion limitation before export.
- **Observed:** no PDF download; visible error says the PDF font cannot render one or more source characters. DOCX and XLSX downloads retained the correction and row removal.
- **Suspected root cause:** PDF font/character coverage in the client-side PDF exporter. The app fails visibly instead of silently corrupting the source wording, but the requested format is unavailable for this tender.

### P1 — Repeated technical specifications burden the operator

- **Reproduce:** inspect NIOT PDF pages 18 and 20 and compare returned response entries.
- **Expected:** preserve one requirement per distinct specification while showing both source locations or an actionable duplicate review signal.
- **Observed:** 12 repeated specification entries appeared as requirements on both the bidder compliance schedule and Annexure I, even though the visible numeric values matched. The source includes a separate duplicate schedule by design; repeated rows add review/export work.
- **Suspected root cause:** duplicate reconciliation does not collapse or clearly group this schedule/annexure pair in the live output.

## Acceptance coverage and remaining unknowns

| Area | Evidence / status |
| --- | --- |
| Small, medium, large PDFs | 18-page user-provided, 25-page public NIOT, and 37-/41-page user-provided cases. The two large runs did not complete. |
| Vector tables and prose | NIOT pages 18–22 and input 1 p.10 visually inspected; input 2 reached table layout mapping before timeout. |
| Repeated requirements | NIOT p18/p20 duplicate schedule compared; duplicates remained. |
| Multi-page and scanned content | Input 3 reached one local OCR page but failed routing; no successful scanned/hybrid tender analysis was established. |
| Numerical accuracy | NIOT duplicated schedule values on p18/p20 visually compared and appeared consistent. No corpus-wide numerical score or exhaustive digit/operator audit was produced. |
| Missing obligations | Input 1 target p.10 exposed the omitted “III-V compatible tips” subpointer. No complete gold set exists for the other files. |
| Fabricated or wrong citations | UI navigation mismatch reproduced. A full row-by-row source-text and coordinate adjudication was not completed. |
| Coverage claims | Input 1 displayed explicit incomplete-coverage warnings; no silent full-document-complete claim was observed in that case. |
| Editing/removal | Verified in the current UI replay and persisted into DOCX and XLSX exports. |
| Refresh/recovery | Correction lost on reload; no recovery path. |
| Upload error/cancellation | 413 size rejection, malformed-PDF failure, and synthetic UI cancellation verified. |
| DOCX/XLSX/PDF | Edited content verified in DOCX/XLSX; PDF failed visibly on source characters. |
| Provider usage | Not surfaced in the completed analysis objects; tokens/cost unknown. |

The 370 unit tests and 26 scripted pipeline cases provide useful contract evidence, but they do not outweigh the reproduced live workflow failures. No implementation fix, deployment, or merge was performed as part of this audit.

## Focused backlog

1. Restore production `APP_ACCESS_PASSWORD` configuration and verify the hosted route before any pilot access.
2. Protect or recover unsaved review state before inviting operators to work through long tenders.
3. Fix and independently re-verify citation-to-page selection and source highlighting.
4. Separate general tender administration/commercial language from technical requirement rows, with clear review disposition for mixed clauses.
5. Make long-document processing resumable or reliably bounded, and isolate routing failures so a single page group does not discard all useful work.
6. Support the tested source characters in PDF export or surface the precise unsupported character before the operator invests in edits.
7. Reconcile repeated schedule/annexure requirements while retaining both citations.
8. Run a source-adjudicated real tender matrix covering OCR, numeric values, missing rows, and the unresolved export/source-navigation cases before reconsidering pilot readiness.
