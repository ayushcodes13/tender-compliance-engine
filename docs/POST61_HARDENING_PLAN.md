# Post-CP61 simplification and reality audit

All canonical checkpoints CP00–CP61 are complete. This plan is a post-build hardening pass whose purpose is to make the repository smaller, easier to reason about, and demonstrably usable end to end.

## Rules

- Every item below is a separate focused PR.
- Each PR starts from the latest merged `main`.
- No PR is merged until CI is green.
- Refactors must preserve product behavior unless the PR explicitly fixes a demonstrated bug.
- Do not add new product subsystems merely because the completed checkpoint plan mentioned them.
- Prefer deletion, consolidation, and direct user-flow improvements over new abstractions.

## Planned PR sequence

| PR | Scope | Exit condition |
| --- | --- | --- |
| A | Repository truth + cleanup | **DONE — PR #72.** Docs match current CP61 implementation; temporary PR artifacts removed; current user-facing gaps recorded. |
| B | Backend simplification | **DONE — PR #73.** Reduced unnecessary backend import coupling without behavior changes; full backend suite remained green. |
| C | Human review UI completion | **DONE — PR #74.** Browser exposes clarification/deviation/override/reopen/comment workflows needed for real review. |
| D | Final matrix/export/submission UI | **DONE — PR #75.** Browser exposes final matrix, XLSX/DOCX/PDF export, and submission lock/approval lifecycle. |
| E | Real end-to-end journey tests | **DONE — PR #76.** Fixed OEM upload → worker integration and added upload-driven regression coverage proving searchable OEM source creation. |
| F | Adversarial hardening + release review | **DONE — PR #77.** Removed unsafe raw-HTML source rendering, added a CI invariant, corrected worker-stage documentation, and published the final manual-review checklist. |

## Product reality test

The target is deliberately simple:

```text
Tender file
  → trustworthy requirements with source locations
  → human review
OEM/vendor file
  → evidence and vendor facts
  → deterministic/grounded comparison
  → human compliance review
  → final compliance matrix/export
```

Anything that does not materially support this flow, trustworthiness, security, or operability is a candidate for simplification or removal.

## Required final report

After PR F, report:

1. what was removed or simplified;
2. what automated E2E paths passed;
3. what adversarial failures were found and fixed;
4. what is still intentionally not automated;
5. the exact manual review steps the product owner must perform before calling the product ready.
