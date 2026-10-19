# Tender Compliance Engine visual system

The interface should feel like a serious technical review workspace used by
engineering, procurement, and bid teams. It must not look like an AI demo.

## Direction

- light, calm, information-dense;
- warm neutral application canvas;
- white review/work surfaces;
- deep ink/navy typography;
- one restrained cobalt primary accent;
- amber only for review attention;
- green/red only for real positive/negative states;
- landing page uses an editorial two-column hero with a clearly labeled illustrative citation preview;
- review workspace keeps requirement counts, source list, PDF page, quote, and human check action visible as one evidence flow;
- generous outer margins and clear panel gutters at desktop sizes, with stacked panels on narrow screens;
- no gradients, glassmorphism, neon, purple AI motifs, decorative chat bubbles,
  or unnecessary floating cards.

## Core colors

| Token | Value | Usage |
|---|---|---|
| background | #f4f6f8 | App/marketing canvas |
| surface | #ffffff | Main work surfaces |
| surface-elevated | #f8fafc | Hover/secondary surfaces |
| border | #dfe4ea | Default dividers |
| border-hover | #c5ced8 | Interactive borders |
| text-primary | #172033 | Main copy |
| text-secondary | #516074 | Supporting copy |
| text-tertiary | #667085 | Metadata |
| accent | #2457d6 | Primary action / selected state |
| accent-hover | #1e49b8 | Primary hover |
| accent-soft | #edf3ff | Selected/quiet accent backgrounds |
| success | #16734a | Confirmed positive state |
| warning | #9a5b00 | Attention/review state |
| error | #b42318 | Confirmed error/non-compliance |

## Components

- Buttons: 6–8px radius, no pill CTAs.
- Tables: visible row/column structure, compact cells, subtle hover.
- Review panes: boundaries come from dividers and whitespace, not floating cards.
- Status: small semantic badges; never use decorative colour.
- Uploads: clear dashed target, direct copy, visible processing state.
- Source/evidence: typography and provenance take priority over decoration.
- Navigation: quiet rail with one clear selected state.

## Motion

Motion is functional only: small fades, loading, and navigation transitions.
Do not use large hover lifts, scaling cards, glowing buttons, or perpetual decorative motion.
Use local system font stacks so the interface does not depend on a third-party font request.

## Product test

A screenshot should plausibly belong to a procurement/compliance tool even if
all AI-related words are removed.
