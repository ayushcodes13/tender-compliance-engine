# Post-CP61 simplification and reality audit

All canonical checkpoints CP00–CP61 are complete. This plan is a post-build hardening pass whose purpose is to make the repository smaller, easier to reason about, and demonstrably usable end to end.

## Rules

- Every item below is a separate focused PR.
- Each PR starts from the latest merged `main`.
- No PR is merged until CI is green.
- Refactors must preserve product behavior unless the PR explicitly fixes a demonstrated bug.
- Do not add new product subsystems merely because the completed checkpoint plan mentioned them.
- Prefer deletion, consolidation, and direct user-flow improvements over new abstractions.
- Real GitHub timestamps are authoritative. Historical reference dates below are planning labels only and are not backdated GitHub metadata.

## Planned PR sequence

| PR | Historical reference slot | Scope | Exit condition |
| --- | --- | --- | --- |
| A | 2026-09-03 | Repository truth + cleanup | Docs match current CP61 implementation; temporary PR artifacts removed; current user-facing gaps recorded. |
| B | 2026-09-05 | Backend simplification | Remove dead/duplicate code and split only the highest-cost god-module boundaries without behavior changes; full backend suite green. |
| C | 2026-09-07 | Human review UI completion | Browser exposes CP57–CP58 clarification/deviation/override/reopen/comment workflows needed for real review. |
| D | 2026-09-09 | Final matrix/export/submission UI | Browser exposes CP59–CP61 final matrix, XLSX/DOCX/PDF export, and submission lock/approval lifecycle. |
| E | 2026-09-11 | Real end-to-end journey tests | Automated user journey proves create project → upload → process → review → OEM evidence → assessment → final artifact/submission. |
| F | 2026-09-13 | Adversarial hardening + release review | Expanded adversarial suite is green; findings fixed; manual-review checklist documents exactly what a human still needs to inspect. |

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
