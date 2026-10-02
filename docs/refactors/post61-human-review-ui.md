# Post-CP61 human compliance review UI

## User outcome

A browser user can provide OEM evidence material and complete the human review actions that already exist in the backend.

## Scope

- add OEM document upload/list client methods and project-page UI;
- add typed client contracts for compliance assessments, review state, conflicts, clarifications, deviations, and comments;
- add a compliance review panel alongside the existing evidence panel;
- support running/loading assessment, confirm, override with reason, reopen, reviewer comments;
- show unresolved conflicts and allow explicit resolution;
- show clarifications and deviations needed for this requirement;
- preserve conservative semantics: missing evidence is never rendered as non-compliance;
- no schema or backend assessment-rule changes unless a browser integration bug proves one is necessary.

## Exit criteria

The web app typechecks/builds and a reviewer can complete the CP57–CP58 human workflow without calling the API manually.
