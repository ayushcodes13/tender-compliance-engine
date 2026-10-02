# Post-CP61 final matrix / export / submission UI

Historical planning slot: 2026-09-09. This is a planning label only; GitHub timestamps stay truthful.

## Scope

- expose CP59 final matrix in the browser;
- expose CP60 XLSX / DOCX / PDF generation and download;
- fix export download MIME type and filename so generated DOCX/PDF artifacts are not served as XLSX;
- expose CP61 submission versions and DRAFT → LOCKED → APPROVED → REVOKED actions;
- preserve unresolved rows in the final view rather than hiding them;
- no new compliance reasoning or schema.

## Exit criteria

A reviewer can finish the project from the browser after requirement review: inspect final rows, export any supported format, create a submission snapshot, lock it, approve it, and inspect/revoke the version.
