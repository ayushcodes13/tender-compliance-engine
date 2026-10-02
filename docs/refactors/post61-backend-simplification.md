# Backend simplification scope

This refactor is behavior-preserving.

## Changes

1. Stop using `tender_compliance_api.extraction.__init__` as a giant eager re-export surface. Runtime and tests should import the exact extraction module they need.
2. Stop using `tender_compliance_api.document.__init__` as an indirection layer for the core service.
3. Split the oversized requirements router by concern where it can be done without changing route paths or response contracts.
4. Do not rewrite migrations, models, comparison logic, evidence semantics, or persistence behavior.
5. Full lint/type/test suite must remain green.

## Explicit non-goals

- no schema changes;
- no product feature changes;
- no removal of Phase 2 capabilities;
- no migration squashing on a repository that now has a completed release history.
