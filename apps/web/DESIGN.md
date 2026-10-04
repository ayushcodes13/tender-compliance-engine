# Design Tokens — Flowsuite / Tender Compliance Engine UI

> Extracted from the [Flowsuite Framer template](https://flowsuite.framer.website/)
> and adapted for the Tender Compliance Engine's dark SaaS aesthetic.

## Colors

| Token | Value | Usage |
|---|---|---|
| `background` | `#0a0a0f` | Page background |
| `surface` | `#111117` | Cards, panels |
| `surface-elevated` | `#17171f` | Elevated cards on hover |
| `border` | `#252530` | Default borders |
| `border-hover` | `#333340` | Hover borders |
| `text-primary` | `#f3f3f5` | Primary text |
| `text-secondary` | `#b8bac1` | Secondary text |
| `text-tertiary` | `#8c8d96` | Tertiary / muted text |
| `accent` | `#ff6c4c` | Primary brand color (CTA, links, active states) |
| `accent-hover` | `#e55a3e` | Hover state for accents |
| `accent-soft` | `rgba(255, 108, 76, 0.08)` | Tint backgrounds |
| `success` | `#10b981` | Success states |
| `warning` | `#f59e0b` | Warning states |
| `error` | `#ef4444` | Error states |

## Typography

| Element | Font | Size | Line Height | Letter Spacing |
|---|---|---|---|---|
| Display (hero h1) | Figtree 700 | `clamp(40px, 5vw, 64px)` | ~1.05 | `-0.03em` |
| Section heading (h2) | Figtree 600 | 42px → 32px | ~1.1 | default |
| Card title (h3) | Figtree 600 | 20px | 1.2 | default |
| Body | Figtree 400 | 18px | 1.6 | default |
| Caption | Figtree 400 | 14px | 1.5 | default |
| Fine print | Figtree 400 | 12px | 1.5 | `0.04em` uppercase |

## Spacing

Reference scale (Tailwind defaults): 4, 8, 12, 16, 24, 32, 48, 64px.

- Section padding: `120px` (desktop) / `80px` (tablet) / `56px` (mobile)
- Container max-width: `1140px`
- Columns: 12-col grid, 24px gutters (desktop) / 16px (mobile)

## Border Radius

| Token | Value |
|---|---|
| `sm` | 6px |
| `md` | 8px |
| `lg` | 12px |
| `xl` | 16px |
| `2xl` | 20px |
| `full` | 9999px |

## Motion

All entrances use `cubic-bezier(0.16, 1, 0.3, 1)` (soft ease-out).

| Animation | Trigger | From → To | Duration | Delay | Stagger |
|---|---|---|---|---|---|
| Section fade-up | scroll-in-view | `opacity:0, y:30 → 1, 0` | 700ms | -50ms | - |
| Hero text reveal | page load | `opacity:0, y:20 → 1, 0` | 800ms | 0ms | 100ms per line |
| Feature card stagger | scroll-in-view | `opacity:0, y:20 → 1, 0` | 600ms | 0ms | 120ms per card |
| Pricing card hover | hover | scale 1 → 1.02 | 200ms | - | - |
| Navbar link hover | hover | `y:0 → -2px` | 200ms | - | - |
| Testimonial autoplay | interval | `x:100% → -100%` | 30s | - | loop |
| Send button pulse | idle state | scale 1 → 1.05 | 2s | - | loop |

## Breakpoints

| Name | Size |
|---|---|
| `sm` | 640px |
| `md` | 768px |
| `lg` | 1024px |
| `xl` | 1280px |
| `2xl` | 1536px |

## Components

All shadcn/ui components live in `components/ui/`. Section components live in
`components/sections/` (one file per section). Page content lives in typed data
objects in `lib/data/`.
