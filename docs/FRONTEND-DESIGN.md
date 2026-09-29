# Frontend Design Direction

## Reference study

The first product UI pass is based on a cross-product review of Bynd's frontends, with the deepest reference being:

- Bynd-ai/industry-report-agentic
- branch: validation-phase-2
- reference commit: f6ceb152793cf7f9d83cb9f662f38728579ea5e5

Additional design-system references reviewed include Bynd-ai/bynd_frontend, Bynd-ai/metric-search, Bynd-ai/vault-frontend, Bynd-ai/company-reports-frontend, Bynd-ai/workflows-frontend, Bynd-ai/alerts-analytics-frontend, and the shared Bynd-ai/bynd-ui package.

This repository does **not** copy a Bynd feature verbatim. It adapts the visual grammar and evidence-review interactions to technical tenders.

## What is consistent across the Bynd products

### Quiet enterprise shell

- warm neutral app canvas rather than a pure-grey dashboard
- white primary work surface
- very subtle warm shadows
- thin borders
- compact radii, usually 4–8px
- restrained blue reserved for primary action/focus
- no decorative gradients or oversized marketing UI inside the application

### Typography

- Inter/system sans for operational UI
- IBM Plex Serif-style editorial heading treatment
- dense 11–14px controls and metadata
- larger type only for true page-level headings

The Tender Compliance Engine uses the same hierarchy but relies on system font fallbacks instead of copying font assets from another repository.

### Layout

- fixed-height application shell
- internal scrolling regions
- compact navigation rail
- dense split panes for document-heavy work
- min-width: 0 / overflow discipline so long file names and technical text do not break the workspace

### Evidence UX

The Industry Reports validation UI is the most important reference.

Useful patterns adapted here:

1. An inline source/citation chip should be small and readable rather than a large card.
2. Hovering a source chip should give a quick evidence glance.
3. Clicking/activating evidence should move the user to the source, not merely show metadata.
4. The currently reviewed finding needs stronger highlighting than the surrounding findings.
5. Review navigation should operate on the whole finding and keep it visible when layout changes.
6. The evidence panel separates:
   - what is being reviewed,
   - why it needs review,
   - where it came from,
   - what the user can do next.
7. Source highlighting should look identical wherever the same source span is represented.

## Tender-specific adaptation

Industry Reports reviews prose claims against evidence. Tender Compliance Phase 1 reviews **extracted requirements against the tender source itself**.

The main review screen therefore uses three panes:

    Requirement navigator
            |
            +-- exact source citation
            |
            v
    Tender document viewer
            |
            +-- highlighted source span
            |
            v
    Review / normalization panel

### Pane 1 — requirements

Shows:

- stable requirement ID
- clause
- category
- mandatory state
- review state
- normalized wording
- source page chip

### Pane 2 — source document

Shows:

- document/version
- page
- source context
- the exact cited phrase highlighted
- a clear current-finding marker

When bounding boxes are available later, the same component can map the highlight to PDF coordinates.

### Pane 3 — review

Shows:

- raw/exact source text
- normalized requirement
- location precision
- OCR warning if present
- notes
- review action

The panel deliberately avoids vendor-compliance states in Phase 1.

## Status colors

Only semantic status uses saturated colors:

- amber: needs review / OCR warning
- green: reviewed
- red: extraction/error states

Blue is brand/action/focus, not "AI magic."

## Current frontend status

This pass is a functional visual prototype backed by local demo data. It demonstrates:

- Bynd-style application shell
- project dashboard
- interactive requirement selection
- review filters
- source chips
- source-glance popover
- exact source highlighting
- next/previous review navigation
- editable normalized requirement
- reviewer notes
- local "mark reviewed" behavior

Persistence/API wiring belongs to the Project/Document/Requirement milestones and should replace the demo data without changing the interaction model.
