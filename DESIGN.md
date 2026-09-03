---
name: printerService
description: The phone-facing control panel for a USB-only printer, styled as an elementary-school exercise book — the interface is written on ruled paper.
colors:
  paper: "#FBF7EE"
  paper-raised: "#FFFFFF"
  rule: "#B7D3EE"
  rule-strong: "#8FB8E4"
  margin-red: "#F0776D"
  ink-blue: "#24418E"
  graphite: "#566072"
  cyan-wet: "#0072A3"
  green-pen: "#1E7A4E"
  red-pen: "#C0392B"
typography:
  display:
    fontFamily: "\"Patrick Hand\", \"Segoe Print\", \"Comic Sans MS\", cursive"
    fontSize: "24px"
    fontWeight: 400
    lineHeight: "32px"
    letterSpacing: "normal"
  heading:
    fontFamily: "\"Patrick Hand\", \"Segoe Print\", \"Comic Sans MS\", cursive"
    fontSize: "19px"
    fontWeight: 400
    lineHeight: "32px"
    letterSpacing: "normal"
  body:
    fontFamily: "system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  mono:
    fontFamily: "ui-monospace, Consolas, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  box: "12px 14px 12px 14px / 14px 12px 14px 12px"
  field: "8px"
  pick: "10px 12px 10px 12px / 12px 10px 12px 10px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  section: "28px"
  margin-column: "52px"
components:
  button-primary:
    backgroundColor: "transparent"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.box}"
    padding: "8px 22px"
    height: "48px"
  button-scan:
    backgroundColor: "transparent"
    textColor: "{colors.cyan-wet}"
    rounded: "{rounded.box}"
    padding: "8px 22px"
    height: "48px"
  file-picker:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.graphite}"
    rounded: "{rounded.pick}"
    padding: "8px 12px"
    height: "44px"
  text-input:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.field}"
    padding: "8px 10px"
    height: "44px"
---

# printerService — Design System

## Overview

**Creative North Star: "The page IS the paper."**

The service moves pixels to paper and back; the UI is an elementary-school
exercise book. A warm sheet carries light-blue ruled lines every 32px and
a 2px red margin line at x=52px (72px on desktop, rule pitch 36px). The
interface is *written on* the sheet: headings sit on the lines, job
entries are lines of "handwriting," and the machine marks the margin like
a teacher — green tick for done, red-pen note for failed, strike-through
for cancelled.

**Key Characteristics:**
- The ruled background is the subject, not decoration (The World-Earned
  Stripe Rule).
- Job state is always three signals: icon + the API's exact word + pen
  color. Color never speaks alone (The Three-Signal Rule).
- The margin column holds only marks; content never enters it.
- One motion element in the whole product: the pencil writing a wavy ink
  line while a job works.

## Colors

Grouped by role:

- **The sheet (surfaces):** `paper` is the page; `paper-raised` (#FFFFFF)
  is reserved for controls that need clean edges — inputs, selects, the
  file picker. Nothing content-shaped gets a white card.
- **The decorative trio (never text, never status):** `rule` (#B7D3EE)
  draws the ruled lines; `rule-strong` (#8FB8E4) underlines section
  headings and borders fields; `margin-red` (#F0776D) draws the vertical
  margin line only.
- **The ink (static text):** `ink-blue` (#24418E, ballpoint) for primary
  text, headings, buttons; `graphite` (#566072, pencil) for secondary
  text, helper copy, and all monospace machine values.
- **The pens (job states):** `graphite` = queued/received,
  `ink-blue` = converting/scanning, `cyan-wet` (#0072A3) = printing,
  `green-pen` (#1E7A4E) = done (the only success color),
  `red-pen` (#C0392B) = failed, `graphite` + strike-through = cancelled.

**The Margin-Red-Is-Not-Error Rule.** The decorative `margin-red` is
visibly lighter than `red-pen`; errors are always `red-pen`. If a mockup
can't tell them apart at a glance, the shades are wrong. No gradient or
wash may reuse these hues.

All six ink/pen colors pass 4.5:1 on both surfaces and are the only
text colors. The decorative trio never carries text.

## Typography

Three voices, one job each:

- **Handwriting** — self-hosted Patrick Hand (OFL, inlined as a base64
  woff2; fallback `"Segoe Print", "Comic Sans MS", cursive`). Page title
  (24px), section headings (19px, sitting on a 2px `rule-strong`
  underline), button labels (19px), status words (16.5px), empty-state
  notes. Never for error detail, helper copy, URLs, or copyable numbers.
- **Body** — system-ui 14px/1.5 in `graphite` for helper and error text.
- **Mono** — ui-monospace 12.5px in `graphite`, only for
  machine-generated values (job IDs, timestamps, DPI, error codes).

**The Short-Handwriting Rule.** If a string needs re-reading, it is set
in the body face. Handwriting carries labels and single words only.

## Layout

Mobile-first; the 390px viewport is the primary surface.

- Header zone: plain paper (no rules behind it), title left, wifi health
  icon right (24px, `cyan-wet` when reachable, `red-pen` when not).
- The sheet starts below the header: red margin line at 52px, ruled lines
  every 32px, content begins at 64px.
- Jobs: one entry per ruled line (two when error text wraps) — a 52px
  margin column for the state mark, then icon + filename + mono id +
  status word written inline. Entries are never boxed or carded; the
  ruled page is the container.
- Desktop (≥768px): same sheet widened to 8vw side margins, margin column
  72px, rule pitch 36px, print/scan actions max-width 560px, jobs flow in
  two columns.

**The Empty-Margin Rule.** The margin column holds state marks only —
never content, never controls.

## Elevation & Depth

None. The world is flat ink on paper; there are no shadows and no
elevation tokens. Controls distinguish themselves with borders and the
`paper-raised` surface, not depth.

## Shapes

- Action buttons: 1.5px ink border with the barely-wobbled "drawn once by
  hand" radius `12px 14px 12px 14px / 14px 12px 14px 12px`, transparent
  fill.
- Fields/picker: 8px radius (picker: slightly wobbled variant), 1px
  `rule-strong` border on `paper-raised`.
- Icons: Phosphor (MIT), inline `<symbol>` sprite, `currentColor`, sizes
  16/20/24px only, weights regular / fill (done tick) — never duotone.
  Icons draw in ink or the state's pen color, never in the decorative
  trio.

## Components

- **Action button** (Print / Scan / Retry): hand-drawn box, handwriting
  label + trailing 20px icon, 48px min height. Scan's box draws in
  `cyan-wet`; disabled = 0.4 opacity; pressed = 7% ink tint fill.
- **File picker**: dashed `rule-strong` border on `paper-raised`, upload
  icon + truncated filename, 44px min height.
- **Job entry**: margin mark (state icon in pen color) + written line
  (format glyph, filename, mono id, handwritten status word). Failed
  entries add graphite error text on a second line. Active entries add a
  44px trash button (DELETE). Cancelled entries strike through name and
  status word.
- **The pencil progress**: inline SVG — pencil + wavy ink line drawn via
  a `stroke-dashoffset` loop (1.6s ease-in-out; `cyan-wet` for printing,
  `ink-blue` for converting/scanning). The product's only looping motion;
  `prefers-reduced-motion` swaps to a static fully-drawn line. Status
  lines lead with the API's exact state word (`queued`, `printing`,
  `done`, `failed`, `cancelled`) — never a synonym, never an emoji.

## Do's and Don'ts

**Do**
- Keep the sheet flat: two CSS gradients draw everything (red margin line
  + ruled lines); no texture images.
- Keep status = icon + exact word + pen color, everywhere.
- Keep every asset inlined/self-hosted — zero runtime CDN calls.
- Keep the margin for marks only.

**Don't**
- No emoji anywhere (test-enforced).
- No cards, shadows, or boxes around job entries.
- No handwriting on long/error/numeric copy; no mono on ordinary labels.
- No graph grid, sticky-note panels, torn edges, or a second paper
  texture.
- No `margin-red` in error semantics; no decorative-trio colors on text.


