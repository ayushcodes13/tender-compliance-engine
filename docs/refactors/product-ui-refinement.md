# Product UI refinement

## Goal

Replace the generic dark-SaaS/glass visual direction with a light, restrained,
technical interface appropriate for procurement, engineering, and bid-review work.

## Visual direction

- warm off-white application canvas;
- white work surfaces with thin neutral borders;
- deep ink/navy typography;
- restrained cobalt blue as the single primary action/accent colour;
- amber only for review attention and green/red only for real status semantics;
- fewer decorative cards and less rounded/pill-heavy UI;
- denser tables and review panes where information density matters;
- no gradients, glassmorphism, neon, purple AI styling, or decorative AI motifs.

## Scope

Presentation only. Compliance logic, API contracts, provenance semantics,
processing states, and database behavior are unchanged.

## Acceptance

- web typecheck succeeds;
- production Next.js build succeeds;
- Docker build succeeds;
- existing workflow remains usable;
- colour contrast and keyboard focus remain clear;
- the interface reads as a technical review product rather than an AI dashboard.
