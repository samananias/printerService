# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One person — the owner — on their Android phone, at home, on the same LAN as
the print server. Their job: "send this file to the printer" and "get that
scan onto my phone," then a quick glance to confirm it finished. Household
members on the same Wi-Fi are occasional secondary users (trusted, shared
PIN). Nobody uses this from outside the home network, ever.

## Product Purpose

Turn a USB-only Epson L3210 all-in-one into a network print/scan station:
the phone's browser sends files to a Python service on an old Windows PC,
which hands them to the Windows print spooler and out over USB; the flatbed
scanner sends pages back the other way as downloads. Success is: open a URL
on the phone, pick a file, tap Print, paper comes out — without ever
touching the PC.

## Positioning

A browser page served by the print server itself — no app to install, no
cloud, no account. A real network printer's firmware plays the role this
Python service plays; on a USB-only printer, the service IS the missing
network half. That "your old PC pretends to be the smart part of the
printer" mechanism is the product.

## Operating Context

- LAN-only home Wi-Fi. The router's internet may be down while the LAN is
  fine — the page must fully work with zero internet reachability.
- The service runs headless on an old/low-spec Windows PC (Task Scheduler,
  before logon). The page is served by FastAPI on port 8000.
- The printer may or may not have a working scanner; the page must degrade
  quietly based on live hardware detection, never by error.
- A shared PIN gates state-changing routes; read-only GETs stay open.

## Capabilities and Constraints

- Print: PDF, images, office documents, TXT/CSV — every format normalized
  to PDF internally. Optional per-job options (copies, pages, paper,
  color_mode). Scan: flatbed, one page per job, optional dpi/color_mode/
  format. Retry and cancel for print jobs.
- Job states use the API's exact vocabulary:
  `received → queued → converting/scanning → printing → done | failed |
  cancelled`. The UI never invents synonyms.
- Technical constraints (binding): vanilla HTML/CSS/JS, no build step, no
  framework; the page is a single self-contained HTML string in
  `app/api/web.py`; no runtime CDN/external calls — all assets self-hosted;
  mobile-first (~390px primary surface); printing is the first thing on the
  page (the Scan section renders only when a scanner is detected).
- Automated tests (`tests/api/test_health_web.py`) pin structural hooks:
  `>Print<`, `id="printBtn"`, `id="scanSection" style="display:none`,
  `id="scanBtn"`, `onclick="startScan()"`, `pollScan`,
  `getElementById("scanDpi"/"scanColorMode"/"scanFormat")`, and the
  `/favicon.svg` link. A restyle must keep these hooks or deliberately
  update the tests in the same change.

## Brand Commitments

- Name: **printerService** (lowercase, one word).
- The existing favicon SVG mark (printer + Wi-Fi waves, cyan/magenta/
  yellow accents) is shipped, referenced by tests, and stays.
- UI copy bans emoji entirely (established design rule — the current page's
  📨/❌/⏳/✅ status markers are legacy debt to remove at the next restyle).
- Status text always uses the API's exact state words.

## Evidence on Hand

- `docs/SOURCE_OF_TRUTH.md` — central decision record (print pipeline,
  architecture, testing).
- `docs/MULTI_FORMAT_PLAN.md`, `docs/SCAN_PLAN.md` — format and scan
  decision records incl. real-hardware spike timings.
- `docs/WEBDESIGN_PLAN.md` — the design brief (restyled 2026-09-03 to the
  elementary-notebook world; v1's print-shop world is retired).
- Live page: `app/api/web.py`; suite: 342 tests, incl. web-page
  structural tests. No marketing assets, testimonials, or press exist —
  none may be fabricated.

## Product Principles

1. The machine's vocabulary is the UI's vocabulary.
2. Degrade by hardware truth, never by error — absent capability means
   quiet absence, not a message.
3. Works with the router's internet down: every asset self-hosted.
4. One phone, one glance: "did it finish?" answered within seconds.
5. Printing first, always.

## Accessibility & Inclusion

- Body text contrast ≥ 4.5:1 against paper surfaces; accent colors get
  darkened text-safe variants.
- Status is never color-only: icon + exact status word always accompany
  color.
- Minimum 44×44px tap targets; visible non-default keyboard focus ring;
  `prefers-reduced-motion` respected everywhere motion is used.
