# printerService Web UI — Design Rules

**What this is:** a design brief you can hand to yourself, a designer, or an
AI coding tool to build/restyle the phone-facing page that FastAPI serves
at `app/api/web.py`. It's written as rules, not as finished HTML — the goal
is a consistent set of decisions anyone building a screen for this app can
follow without re-deciding the same things twice.

**Revision 2 (2026-09-03).** v1 of this brief dressed the page as a print
shop (registration marks, CMYK calibration bars). The owner replaced that
world: the page is now a **school exercise book**. v1's registration-mark
spinner, CMYK-as-decoration rules, and print-shop vocabulary are retired;
what survives is everything the two worlds share — the functional state
colors, the API's exact vocabulary, self-hosted assets, and every
constraint in §0.

---

## 0. Grounding — what this actually is

Before any color or icon: this is a **control panel for a machine**, not a
marketing site. One person, on their phone, checking "did my thing print /
scan yet." The service already has real constraints worth designing *with*,
not against:

- **LAN-only, no internet exposure.** The page must render and work
  correctly with zero external network calls at runtime — no CDN fonts,
  no CDN icon scripts, nothing that silently breaks if the router's
  internet is down but the LAN is fine. Self-host everything.
- **Vanilla HTML/CSS/JS, no build step.** The codebase's own rule is
  "prefer simple technologies" (SOURCE_OF_TRUTH §18) and the web page is
  already vanilla-JS by convention. Don't introduce a framework or a
  bundler for styling — plain CSS with custom properties.
- **Real job states drive the UI**, not invented ones:
  `received → queued → converting/scanning → printing → done | failed | cancelled`.
  Use these exact words in the UI — they're already the API's vocabulary
  (SCAN_PLAN §5, MULTI_FORMAT_PLAN §8), so button labels, statuses, and
  toasts should never invent synonyms for the same state.
- **Mobile is the primary surface**, not a breakpoint you remember at the
  end. Design the ~390px viewport first; treat desktop as the enhancement.
- **Test-pinned hooks survive.** `tests/api/test_health_web.py` asserts
  specific ids and strings (`printBtn`, `scanSection` hidden by default,
  `startScan`, `pollScan`, the scan option ids, `>Print<`). The restyle
  keeps these hooks; if a hook must move, the test changes in the same
  commit, never silently.

---

## 1. The one idea

The service's whole job is a handoff between the physical and the digital:
paper → pixels (scan), pixels → paper (print). So the page **is the
paper**: an elementary-school exercise book — warm sheet, light-blue ruled
lines, the red margin line down the left — and the interface is *written
on it*. Headings sit on the lines like a date written at the top of a
page. Jobs aren't cards floating on a dashboard; they're entries written
on the ruled lines, and the machine marks them the way a teacher marks a
page: a green tick in the margin when it's done, a red-pen note when it
failed, a strike-through when it was cancelled.

The tone is a **well-kept notebook, not a doodle pad**: legible, aligned
to the rules, playful only in the lettering and the one signature element
(§5). Everything functional stays utilitarian.

Spend the one deliberate flourish on the **pencil progress** (§5) — a
pencil that writes a wavy ink line while a job works. Everything else on
the page stays quiet.

---

## 2. Color

The sheet is the background; ink carries the meaning. Ruled lines and the
red margin are **structure, not color-coding** — they never double as
status indicators.

### Sheet and ink (the world)

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#FBF7EE` | The exercise-book sheet — warm, slightly cream |
| `--paper-raised` | `#FFFFFF` | Inputs, selects, pop-ups — anything that must sit cleaner than the sheet |
| `--rule` | `#B7D3EE` | The light-blue ruled lines (decorative, always decorative) |
| `--rule-strong` | `#8FB8E4` | Heavier rule under section headings, the "top-of-page" double line |
| `--margin-red` | `#F0776D` | The vertical margin line (decorative). NOT the error color — see `--red-pen` |
| `--ink-blue` | `#24418E` | Ballpoint blue — primary text, headings, button labels |
| `--graphite` | `#566072` | Pencil grey — secondary text, timestamps, helper copy |

### Pen colors (function — mapped to job states)

State colors are ink the machine writes with. They keep v1's
color-is-a-state-signal discipline; only the cast changed:

| Token | Hex | State | Margin annotation (§6) |
|---|---|---|---|
| `--graphite` | `#566072` | `queued` | clock icon + word, waiting |
| `--ink-blue` | `#24418E` | `converting`, `scanning` | the pencil element at work |
| `--cyan-wet` | `#0072A3` | `printing` | "fresh ink" — the one cyan survivor |
| `--green-pen` | `#1E7A4E` | `done` | the teacher's tick — the **only** success color |
| `--red-pen` | `#C0392B` | `failed` | the teacher's red note |
| `--graphite` | `#566072` | `cancelled` | entry struck through, `prohibit` icon |

**Rules:**

- `--rule`, `--rule-strong`, `--margin-red` are **never** used for text,
  buttons, or status. They draw the page; they don't speak.
- `--margin-red` ≠ error. Errors are `--red-pen`, which is visibly darker
  and redder. If a reader can't tell them apart at a glance, the shades
  are wrong.
- `--green-pen` is reserved for confirmed success exactly as v1 reserved
  its green — nothing "in progress" ever wears it.
- All six pen colors are text-safe on `--paper` (≥ 4.5:1 at the sizes in
  §3). If you introduce a lighter accent variant, it may be used only for
  icons/fills, never for text.
- **The ruled background is world-earned, not generic striping:** this page
  literally *is* ruled paper — the stripes are the subject, the same way
  blueprint grid is earned by a blueprint. Still: keep them faint
  (`--rule` at full opacity only on the 1px line, nothing stronger), keep
  text baseline-aligned to them where practical, and never run other
  backgrounds (sticky-note yellow, graph grid) on the same sheet.
- Cancelled jobs are communicated **three ways at once**: graphite color,
  `prohibit` icon, and a strike-through on the entry — never
  strike-through alone.

### Recipes

```css
/* The sheet: red margin line + light-blue rules every 32px.
   The first rule sits below the page header; the header zone stays plain. */
.page {
  background-color: var(--paper);
  background-image:
    linear-gradient(90deg,
      transparent 0 52px,
      var(--margin-red) 52px calc(52px + 2px),
      transparent calc(52px + 2px)),
    repeating-linear-gradient(to bottom,
      transparent 0 31px, var(--rule) 31px 32px);
}

/* Header zone (plain, no rules) sits above .page or is masked out;
   on desktop the margin line moves to 72px and the rules to 36px pitch. */
```

---

## 3. Type

Three voices, each with one job. Only the handwriting face needs a font
file; mono and body run off system stacks so the page stays light.

- **Handwriting — self-hosted, exactly one face:** **Patrick Hand** (OFL,
  single 400 weight — genuinely notebook-lettered, still legible at UI
  sizes). Download the `.woff2` **once**, commit under
  `app/static/fonts/`, `@font-face` with `font-display: swap`. Fallback
  stack: `"Patrick Hand", "Segoe Print", "Comic Sans MS", cursive`.
  Handwriting is the page's voice for: page title, section headings,
  button labels, status words, empty-state notes. **Never** for: error
  detail, helper copy, URLs, or anything numeric that must be copied —
  long handwriting is hard to read and reads as a theme costume.
- **Body — system:** `system-ui, sans-serif` at 14–15px/1.5 for helper
  copy, error detail, and any sentence longer than a label. Body text is
  `--graphite`; emphasis within body is weight, not color.
- **Mono — system:** `ui-monospace, monospace`, **only** for
  machine-generated values: job IDs, timestamps, DPI, HRESULT/error codes,
  at 13px in `--graphite`. Same scoping rule as v1 — monospace-as-
  decoration for ordinary labels stays banned.

Scale (mobile base; sizes are set so a handwriting heading sits *on* a
32px rule):

| Use | Face / size / weight |
|---|---|
| Page title | handwriting, 24px (spans ~1.5 rules) |
| Section heading | handwriting, 18px, `--ink-blue`, sits on a `--rule-strong` underline |
| Status word (per job) | handwriting, 16px, in the state's pen color |
| Button labels | handwriting, 18px |
| Body / helper / error detail | system, 14px/1.5, `--graphite` |
| Job ID / timestamp / DPI / codes (mono) | system mono, 13px, `--graphite` |

**Avoid (unchanged from v1, still true here):** tracked-out ALL-CAPS
labels, middle-dot-joined meta strings, em-dash labels ("STATUS —
queued"), trailing arrows on buttons. Every label says only what it needs
to. New for v2: no faux-handwriting effects on system fonts (no
`font-style: italic` pretending to be script, no "marker" text-shadows).

---

## 4. Icons — rules

**No emoji, anywhere.** Not in buttons, statuses, toasts, error messages,
or empty states. This is a hard rule — and the *current* page ships emoji
status markers (`📨 ❌ ⏳ ✅`); replacing them with the system below is an
explicit, required part of implementing this brief.

- **Icon set: [Phosphor Icons](https://phosphoricons.com)** (MIT, carried
  over from v1 — the set is world-neutral utility). Download the specific
  SVGs **once**, flat single-color outline files — never the webfont, never
  a CDN script — committed under `app/static/icons/`.
- **Four weights, each meaning one thing — weight is a state signal:**

  | Weight | Meaning | Example |
  |---|---|---|
  | `thin` | Disabled / unavailable | Scan controls just before the section hides |
  | `regular` | Default / idle | Everything at rest |
  | `bold` | Active / selected / hover | The Print button while pressed |
  | `fill` | Confirmed, persistent state | A job's `done` tick |

  **Never `duotone`** — icons use `currentColor` so their color comes from
  the state token, not the file.
- Size scale: 16 / 20 / 24px only. One icon *concept* per action
  everywhere it appears; weight may change with state, the glyph does not.
- Icons draw in **ink**: default `--ink-blue`; state-bearing icons take
  their job's pen color. Icons never draw in `--rule`/`--margin-red`.

**Mapping (carried over, print-shop references removed):**

| Concept | Icon |
|---|---|
| Upload / file picker | `upload-simple` |
| Print action | `printer` |
| Scan action | `scan` |
| PDF / image / doc / xls / ppt / txt / csv files | `file-pdf`, `file-image`, `file-doc`, `file-xls`, `file-ppt`, `file-txt`, `file-csv` (the job list shows *which* format ran — a real MULTI_FORMAT_PLAN capability) |
| Job queued | `clock` |
| Converting / scanning / printing (in progress) | the pencil element (§5), not a Phosphor icon |
| Done | `check-circle` → `-fill` once done (the teacher's tick) |
| Failed | `x-circle` |
| Cancelled | `prohibit` |
| Retry | `arrow-clockwise` |
| Download result | `download-simple` |
| Delete / cancel job | `trash` |
| Options drawer | `sliders-horizontal` |
| Copies / pages / color mode | `copy`, `rows`, `drop` |
| DPI | `focus` |
| PIN | `lock-key` |
| Server health | `wifi-high` (`wifi-slash` when unreachable) |
| Empty state (no jobs yet) | none — a blank stretch of ruled page with one short handwritten note ("Nothing here yet."), nothing icon-shaped |

---

## 5. The signature element — the pencil progress

v1's registration-mark spinner is **retired**. The one orchestrated motion
element is a **pencil writing a wavy ink line** — the machine doing its
homework. Built once as inline SVG + CSS (no JS animation loop needed);
crisp vector linework, not an illustration.

One compact component (~24×24 icon zone + a ~64px line it writes) used in
the margin column of any `converting` / `scanning` / `printing` entry, and
larger (~48px + full-width line) as the page-level "working" indicator.

States (all also carry the exact status word — the pencil never speaks
alone):

- **In progress:** a small pencil (blue ink body, graphite tip) bobs
  subtly along the top of a wavy line that draws itself left→right with a
  `stroke-dashoffset` loop, in the state's pen color (`--ink-blue` for
  converting/scanning, `--cyan-wet` for printing).
- **Done:** the wave completes into one underline stroke beneath the
  status word; the pencil lifts away; a `check-circle-fill` tick lands in
  the margin in `--green-pen` (one short 150–200ms crossfade, not a pop).
- **Failed:** the line is overdrawn with a two-stroke red scribble
  (`--red-pen`) — the page's way of crossing out a wrong answer — with the
  `x-circle` and the word `failed`.
- **Queued:** no pencil; the clock icon and word in graphite.
- **Cancelled:** the entry's line is struck through once in graphite.

```css
/* Motion contract: one authored moment (the writing loop), 1.6s ease-in-out,
   and nothing else on the page loops. */
@media (prefers-reduced-motion: reduce) {
  /* No bobbing, no drawing loop: static states only —
     in-progress shows the line fully drawn + static pencil. */
}
```

---

## 6. Layout & responsiveness

**Mobile first, literally** — design the 390px layout, then add
breakpoints. The app is **two pages of the same sheet**: `/` (print) and
`/scan` (scan), each written on the same ruled rules, each reachable from
the other by an always-visible nav box in the header (Scan on the print
page, Print on the scan page). The scan page degrades to one calm status
line until a scanner is actually detected; the print page carries no scan
UI at all.

```
MOBILE (base, ~375–430px) — PRINT PAGE (/)
┌──┬──────────────────────────┐
│  │ printerService  [Scan] [wifi] │ ← header: handwriting title, the
│  │                          │   always-visible Scan nav box, health
├──┼──────────────────────────┤ ← red margin line starts here
│▍ │ Print            [printer] │ ← action rows written ON the rules,
│▍ │                           │   not boxed cards; a --rule-strong
│▍ │ Options [sliders] ▾       │   line separates sections like a new
│▍ │ Jobs                      │   exercise; options collapsed by default
│ ✓│ check-circle done  #a1b2 [dl] │ ← margin column (left of the red
│▍ │ (next entry)               │   line) holds the annotation only;
│ ✗│ x-circle failed   #9f3c    │   entries are written right of it
└──┴──────────────────────────┘

MOBILE — SCAN PAGE (/scan, same sheet)
┌──┬──────────────────────────┐
│  │ printerService [Print] [wifi] │ ← nav hand-off back to printing
├──┼──────────────────────────┤
│▍ │ Scan              [scan]  │ ← the scan form; its options drawer
│▍ │   Resolution ▾            │   (dpi/color/format) collapsed
│▍ │   Color ▾                 │   until opened; the "no scanner"
│▍ │   Format ▾                │   line replaces all of this when
│▍ │                           │   the hardware isn't there
└──┴──────────────────────────┘
```

- **The nav hand-off.** The header carries one small drawn-box nav button
  pointing at the other page: **Scan** (`--cyan-wet`) on the print page,
  **Print** (`--ink-blue`) on the scan page. Both stay visible regardless
  of hardware — a scanner-less setup simply means the scan page shows a
  single calm status line and no controls.

- **The margin column (~52px, left of the red line)** is where the machine
  marks the page: the state annotation per job (§2's table). It holds only
  marks — never content, never controls.
- **Job entries are written on the rules, not boxed:** one entry = one
  32px rule line (two when error detail wraps): format icon + mono job ID
  + handwritten status word in the pen color. No card, no border, no
  shadow — the ruled page IS the container. Done entries append the
  `download-simple` link at the row's right (44×44px target). This
  replaces v1's ticket cards *and* avoids the generic
  card-with-colored-left-edge treatment entirely.
- **Actions are words with a drawn box:** the Print/Scan actions get a
  1.5px `--ink-blue` border with a barely-wobbled radius
  (`border-radius: 12px 14px 12px 14px / 14px 12px 14px 12px`) — a box
  drawn by hand once, not a sketch effect. Minimum 44×44px, no
  exceptions. Scan's box draws in `--cyan-wet` when a scanner is
  available. No fill, no gradient.
- **Options drawer** (`copies`/`pages`/`paper`/`color_mode` for print;
  `dpi`/`color_mode`/`format` for scan) stays collapsed by default on
  mobile: a `sliders-horizontal` + handwritten label row that expands in
  place; form controls sit on `--paper-raised` fields — the one place
  raised white earns its keep, because controls need clean edges.
- **DESKTOP (≥768px):** same content, wider sheet — margin column to
  72px, rule pitch to 36px, options inline, jobs as a two-column flow of
  written entries. Not a redesign.

---

## 7. Motion

- The pencil progress (§5) is the one orchestrated motion element.
- State transitions (status word + pen color changing) get a short
  150–200ms crossfade, not a slide or bounce.
- No scroll-triggered fade-ins, no per-entry hover lift — a single-screen
  utility; motion only ever answers something the user did or the job
  actually did.
- Respect `prefers-reduced-motion` everywhere motion is used.

---

## 8. Accessibility & quality floor

- **Contrast:** body text ≥ 4.5:1 against `--paper` and
  `--paper-raised`. The six pen colors are chosen text-safe; the
  decorative trio (`--rule`, `--rule-strong`, `--margin-red`) never
  carries text, so its contrast is irrelevant by design. Handwritten
  headings are large text (≥3:1 floor still met — `--ink-blue` far
  exceeds it).
- **Handwriting legibility floor:** handwriting is only for short labels
  and single words (§3). If a string needs re-reading, it's set in the
  body face — this rule protects screen-glancers *and* users with low
  vision; it is not an aesthetic call.
- **Visible keyboard focus ring on every interactive element** — 2px
  `--ink-blue` outline with a 2px offset (never `--rule`/`--margin-red`;
  they're decorative). On `--paper-raised` fields, same ring.
- **Status is never color-only:** icon + exact word + color, always —
  including cancelled's strike-through.
- **Decorative layers are hidden from assistive tech:** the ruled
  background, margin line, and margin annotations' purely decorative
  strokes get `aria-hidden` / background-image treatment, so screen
  readers hear "job done", not "blue line, red line".
- All icons get `aria-label`s describing the action ("Cancel print job",
  not "trash icon").

---

## 9. Do / Don't checklist

**Do**
- Use the job lifecycle's real words as the UI's words.
- Self-host every font and icon file; zero runtime CDN calls.
- Keep the pencil progress as the one bold, custom element.
- Write entries on the ruled lines; keep the margin for marks only.
- Use mono type only for machine-generated values (IDs, codes, DPI).
- Design the phone layout first.
- Keep the test-pinned hooks (`printBtn`, `scanSection`, `startScan`,
  `pollScan`, scan option ids) or update their tests in the same commit.

**Don't**
- No emoji as icons, statuses, or decoration, anywhere — including
  replacing-but-keeping the current page's emoji status strings.
- No external CDN calls at runtime (fonts, icons, or otherwise).
- No ruled-line/graph-paper backgrounds stronger than `--rule`, no graph
  grid, no sticky-note panels, no torn-paper edge images, no paper-texture
  photos — the sheet is drawn with two CSS gradients, flat.
- No handwriting on error detail, helper copy, URLs, or numeric values.
- No numbered 01/02/03 section markers.
- No invented synonyms for job states the API already names.
- No cards, shadows, or boxed containers around job entries — the ruled
  page is the container.
- No gradient washes; no `--margin-red` anywhere near error semantics.

---

## 10. Quick reference

```css
:root {
  /* the sheet */
  --paper: #FBF7EE;
  --paper-raised: #FFFFFF;
  --rule: #B7D3EE;          /* decorative only */
  --rule-strong: #8FB8E4;   /* decorative only */
  --margin-red: #F0776D;    /* decorative only — NOT the error color */

  /* the ink */
  --ink-blue: #24418E;      /* primary text, headings, buttons */
  --graphite: #566072;      /* secondary text, mono values */

  /* the pens (job states) */
  --cyan-wet: #0072A3;      /* printing */
  --green-pen: #1E7A4E;     /* done — the only success color */
  --red-pen: #C0392B;       /* failed */

  /* the voices */
  --font-hand: "Patrick Hand", "Segoe Print", "Comic Sans MS", cursive;
  --font-body: system-ui, sans-serif;
  --font-mono: ui-monospace, monospace;

  /* the drawn box for actions */
  --box-radius: 12px 14px 12px 14px / 14px 12px 14px 12px;
}
```

```css
/* the sheet */
.page {
  background-color: var(--paper);
  background-image:
    linear-gradient(90deg,
      transparent 0 52px,
      var(--margin-red) 52px calc(52px + 2px),
      transparent calc(52px + 2px)),
    repeating-linear-gradient(to bottom,
      transparent 0 31px, var(--rule) 31px 32px);
}
```

---

## 11. Implementation notes (as built, 2026-09-03)

- **Assets are inlined, not mounted — revision to the original note.** The
  page keeps the codebase's single-self-contained-HTML-string philosophy:
  `app/api/web.py` reads the committed font
  (`app/static/fonts/patrick-hand-latin.woff2`) and icon SVGs
  (`app/static/icons/*.svg`, Phosphor) **at import time** and inlines them
  — the font as a base64 data-URI in `@font-face`, the icons as one
  `<symbol>` sprite. No `StaticFiles` mount, no extra requests, icons take
  `currentColor` so job states recolor them, and a missing asset degrades
  silently (system font stack / absent symbol, never a crash).
- **The old page's emoji status strings are gone** — replaced by the
  icon/word/pen-color system in §4; pinned by
  `TestNotebookRedesign.test_page_uses_no_emoji`.
- **A Jobs list was added** (the brief's §6 Jobs section): `GET /jobs`
  (already served by `app/api/jobs.py`) rendered as entries written on the
  rules — per-state margin marks, format glyphs from `job.format`/
  filename, and a cancel (DELETE) button on active entries. Refreshed on
  load, on job events, and every 5 s.
- **Scan lives on its own page** at `GET /scan` (owner request: "make it
  like a different page but still have an accessible button for it"). The
  print page's header carries an always-visible drawn-box **Scan** nav
  button (`--cyan-wet`) linking over; the scan page carries a **Print**
  nav button back. Both pages assemble from the same CSS/JS parts — the
  scan JS only runs on the scan page (guarded by `#scanSection`'s
  presence), so the print page keeps no scan code paths. The scan page
  degrades to one calm status line ("No scanner detected — the printer
  may be off or unplugged.") until `GET /scanners` reports a scanner.
- **Pinned hooks kept verbatim** (§0): `>Print<`, `id="printBtn"`,
  `id="scanSection" style="display:none`, `id="scanBtn"`,
  `onclick="startScan()"`, `pollScan`,
  `getElementById("scanDpi"|"scanColorMode"|"scanFormat")`,
  `href="/favicon.svg"` — zero test changes were needed for the restyle;
  the new tests only *add* pins.
- **Fetch/FormData logic untouched** — upload, polling cadence, and the
  innerHTML-safety rule (nothing from the server enters `innerHTML`
  except the server-issued job id in the scan download link) all carry
  over unchanged. (The PIN-header half of this line was later superseded
  by the login gate — §12.)
- The favicon SVG stays as-is (PRODUCT.md brand commitment) — its cyan/
  magenta/yellow accents are the print-service mark, not the page theme.
- The durable visual system is recorded in `DESIGN.md` +
  `.impeccable/design.json`; product truth in `PRODUCT.md`.

---

## 12. Addendum — the login gate (2026-09-04)

The PIN login gate (full decision record: [LOGIN_PLAN.md](LOGIN_PLAN.md))
is a **third page of the same notebook**, not a dialog: a full-viewport
takeover reusing the identical `.top` header zone and ruled `.sheet`
background, hidden by default (`class="gate hidden"`) and revealed only
when `GET /auth/status` reports `pin_required: true` and no valid stored
session token.

- **No new visual vocabulary.** No card, no shadow, no dimmed backdrop —
  the "no boxed containers" rule holds. The heading sits on the first
  rule like any other `.rulehead`; the field is the standard
  `--paper-raised` input; the Unlock button is the existing drawn-box
  `.btn`. Icon: `lock-key` (already in the §4 mapping — no new icon).
- **New pinned hooks** (same convention as `startScan()`/`scanBtn`):
  `id="pinOverlay"`, `id="pinInput"`, `id="pinRemember"`,
  `id="pinError"`, `onclick="submitLogin()"` — pinned by
  `TestLoginGate` in `tests/api/test_health_web.py`.
- **The old per-action PIN field is gone.** Revision 2's inline
  `id="pin"` field on both pages was removed: the raw PIN is submitted
  exactly once to `POST /auth/login`, the returned opaque token is
  stored client-side (`localStorage` vs `sessionStorage` per the
  Remember checkbox, namespaced key `printerService.pinToken`), and
  every request sends it in `X-Session-Token` via one shared
  `authHeaders()` helper.
- **Error text never uses the handwriting face** (§3 rule): "Incorrect
  PIN." renders through `.status.err` — system font, `--red-pen`.
- **It genuinely blocks the page** (unlike every convenience overlay
  here): `role="dialog"`, `aria-modal="true"`, autofocus, Tab focus
  trap.
- Gate markup + JS are shared by both pages — assembled into `PAGE` and
  `SCAN_PAGE` from one `GATE_HTML` block, the same way the nav hand-off
  is shared.

---

*Revision 2 — the exercise-book world, decided by the owner 2026-09-03
("elementary: paper with blue-red-blue lines"); §12 addendum (the login
gate) 2026-09-04. Product truth lives in `PRODUCT.md`; this file owns
the visual world. v1 (print shop) is retired but its state-color
discipline and constraint set survive here.*





