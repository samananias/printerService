"""GET / — the mobile web page (SOURCE_OF_TRUTH §6 "Option B"; redesign per
docs/WEBDESIGN_PLAN.md **revision 2**: the elementary-school exercise-book
theme — a warm sheet with light-blue ruled lines and a red margin line that
the interface is written ON; job states are ink colors; the one motion
element is a pencil writing a wavy line while a job works).

The page is still a single self-contained HTML string (inline CSS + vanilla
JS — no build tools, no frameworks) served directly by FastAPI, per the
codebase's "prefer simple technologies" rule. That includes its two assets:

- **Font** — Patrick Hand (OFL), committed at
  app/static/fonts/patrick-hand-latin.woff2 and inlined below as a base64
  data-URI at import time, so the page needs no static-file mount and works
  even when the router's internet (or the static dir) is gone.
- **Icons** — Phosphor (MIT), committed as flat SVGs under
  app/static/icons/ and assembled into one inline <symbol> sprite at import
  time, so icons take their color from currentColor and job states can
  recolor them.

Both asset steps degrade silently: missing files fall back to system fonts
/ an empty sprite without breaking the page.

How the upload works (worth reading slowly — this is HTTP from the browser's
point of view):
  1. the styled picker is a <label for="file"> over a hidden
     <input type="file">; JS gets a File object.
  2. FormData() wraps it into a multipart/form-data body — the exact same
     format curl sent in our Phase 4 tests (field name must be "file",
     matching app/api/print.py's parameter).
  3. fetch("/print", { method: "POST", body: formData }) sends it. Note:
     we deliberately do NOT set Content-Type — the browser must add the
     multipart boundary itself; setting it manually breaks the request.
  4. The response is the JSON from POST /print, which we display.

The JS logic (upload, session-token auth, polling, scan detection,
innerHTML safety) carries over from the previous page — this revision
restyled presentation and status rendering (emoji status markers are
gone: status is icon + exact API word + pen color), and added a Jobs list
(GET /jobs, already served by app/api/jobs.py) written on the ruled lines
with per-state ink colors and a cancel button for active jobs. The PIN
login gate (docs/LOGIN_PLAN.md) then replaced the old type-it-every-time
PIN field: the raw PIN is submitted once to POST /auth/login, the opaque
token it returns is stored client-side, and every request sends it in
X-Session-Token via the shared authHeaders() helper.
"""

import base64
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

router = APIRouter()

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# The page's icon vocabulary (WEBDESIGN_PLAN §4). Names become sprite ids
# ("i-<name>"); values are the committed Phosphor SVG files.
ICONS = {
    "printer": "printer.svg",
    "scan": "scan.svg",
    "pencil": "pencil.svg",
    "upload-simple": "upload-simple.svg",
    "clock": "clock.svg",
    "check-circle-fill": "check-circle-fill.svg",
    "x-circle": "x-circle.svg",
    "prohibit": "prohibit.svg",
    "arrow-clockwise": "arrow-clockwise.svg",
    "trash": "trash.svg",
    "sliders-horizontal": "sliders-horizontal.svg",
    "copy": "copy.svg",
    "rows": "rows.svg",
    "drop": "drop.svg",
    "crosshair": "crosshair.svg",
    "lock-key": "lock-key.svg",
    "wifi-high": "wifi-high.svg",
    "wifi-slash": "wifi-slash.svg",
    "file-pdf": "file-pdf.svg",
    "file-image": "file-image.svg",
    "file-doc": "file-doc.svg",
    "file-xls": "file-xls.svg",
    "file-ppt": "file-ppt.svg",
    "file-txt": "file-txt.svg",
    "file-csv": "file-csv.svg",
}


def _font_data_uri() -> str:
    """The handwriting face, inlined as a data: URI (self-hosted, zero
    requests). A missing file returns "" — the CSS then falls back to the
    system handwriting stack."""
    path = _STATIC_DIR / "fonts" / "patrick-hand-latin.woff2"
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return "data:font/woff2;base64," + base64.b64encode(raw).decode("ascii")


def _icon_sprite() -> str:
    """One hidden <svg> holding every icon as a <symbol>, assembled from
    the committed files. Phosphor SVGs are single-path fill=currentColor,
    so stripping the outer tag and re-wrapping preserves the glyph while
    letting CSS color it per state."""
    parts = []
    for name, filename in ICONS.items():
        try:
            raw = (_STATIC_DIR / "icons" / filename).read_text(encoding="utf-8")
        except OSError:
            continue  # missing icon → absent symbol → blank spot, no crash
        inner = raw.split(">", 1)[1].rsplit("</svg>", 1)[0]
        parts.append(f'<symbol id="i-{name}" viewBox="0 0 256 256">{inner}</symbol>')
    if not parts:
        return ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none" '
        'aria-hidden="true">' + "".join(parts) + "</svg>"
    )

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 512 512" width="512" height="512"
     role="img" aria-labelledby="ps-title ps-desc">
  <title id="ps-title">PrinterService</title>
  <desc id="ps-desc">A smartphone feeding into a printer printing a Wi-Fi page.</desc>
  <g id="printerservice-mark" transform="translate(256 256) scale(1.15) translate(-256 -256)">
    <rect id="body" x="112" y="197" width="288" height="174" rx="30" fill="#24272E"/>
    <rect id="page" x="194" y="325" width="124" height="120" rx="10" fill="#FFD84D"
          stroke="#1A1C20" stroke-width="9"/>
    <rect id="output-slot" x="188" y="319" width="136" height="14" rx="7" fill="#FFFFFF"/>
    <g id="wifi" fill="none" stroke="#00AEEF" stroke-width="8" stroke-linecap="round">
      <path d="M 228.4 399.4 A 39 39 0 0 1 283.6 399.4"/>
      <path d="M 236.9 407.9 A 27 27 0 0 1 275.1 407.9"/>
      <path d="M 245.4 416.4 A 15 15 0 0 1 266.6 416.4"/>
    </g>
    <circle id="wifi-dot" cx="256" cy="427" r="6.5" fill="#00AEEF"/>
    <rect id="input-slot" x="184" y="207" width="144" height="22" rx="11" fill="#FFFFFF"/>
    <g id="phone">
      <rect x="204" y="67" width="104" height="160" rx="26" fill="#E6007E"/>
      <rect x="216" y="81" width="80" height="112" rx="13" fill="#FFFFFF"/>
      <rect x="236" y="207" width="40" height="6" rx="3" fill="#FFFFFF"/>
    </g>
    <rect id="input-slot-lip" x="184" y="221" width="144" height="8" fill="#24272E"/>
    <circle id="led" cx="350" cy="267" r="9" fill="#00AEEF"/>
  </g>
</svg>"""

PAGE_CSS1 = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="alternate icon" type="image/svg+xml" href="/favicon.ico">
<title>printerService</title>
<style>
  /* ---- the exercise-book tokens (WEBDESIGN_PLAN §10) ---- */
  :root {
    --paper: #FBF7EE;         /* the sheet */
    --paper-raised: #FFFFFF;  /* controls that need clean edges */
    --rule: #B7D3EE;          /* ruled lines — decorative only */
    --rule-strong: #8FB8E4;   /* heavier rule — decorative only */
    --margin-red: #F0776D;    /* margin line — decorative, NOT errors */
    --ink-blue: #24418E;      /* ballpoint: primary text, headings, buttons */
    --graphite: #566072;      /* pencil: secondary text, mono values */
    --cyan-wet: #0072A3;      /* printing */
    --green-pen: #1E7A4E;     /* done — the only success color */
    --red-pen: #C0392B;       /* failed */
    --font-hand: "Patrick Hand", "Segoe Print", "Comic Sans MS", cursive;
    --font-body: system-ui, sans-serif;
    --font-mono: ui-monospace, Consolas, monospace;
    --box-radius: 12px 14px 12px 14px / 14px 12px 14px 12px;
  }
  @font-face {
    font-family: "Patrick Hand";
    font-style: normal;
    font-weight: 400;
    font-display: swap;
    src: url(__FONT_DATA_URI__) format("woff2");
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { background: var(--paper); color: var(--ink-blue);
         font-family: var(--font-body); }
  :focus-visible { outline: 2px solid var(--ink-blue); outline-offset: 2px;
                   border-radius: 4px; }
/* __CSS2__ */
"""
PAGE_CSS2 = """
  /* ---- header zone: plain paper, no rules ---- */
  .top { display: flex; align-items: center; justify-content: space-between;
         padding: 14px 16px 12px; background: var(--paper); }
  .brand { display: flex; align-items: center; gap: 9px; }
  .brand img { width: 26px; height: 26px; }
  h1 { font-family: var(--font-hand); font-weight: 400; font-size: 24px;
       margin: 0; }
  .health { color: var(--graphite); width: 24px; height: 24px; }
  .health.up { color: var(--cyan-wet); }
  .health.down { color: var(--red-pen); }

  /* ---- the sheet: red margin line + light-blue rules ---- */
  .sheet {
    background-color: var(--paper);
    background-image:
      linear-gradient(90deg, transparent 0 52px,
        var(--margin-red) 52px calc(52px + 2px),
        transparent calc(52px + 2px)),
      repeating-linear-gradient(to bottom,
        transparent 0 31px, var(--rule) 31px 32px);
    margin: 0 10px 30px;
    padding: 12px 12px 46px 0;
    min-height: 70vh;
  }
  section, .act { margin: 0 0 28px 64px; }
  .jobs { margin-left: 0; }
  .rulehead { font-family: var(--font-hand); font-weight: 400;
              font-size: 19px; margin: 0 0 10px; padding: 0 8px 3px 0;
              display: inline-block;
              border-bottom: 2px solid var(--rule-strong); }
  .jobs .rulehead, .empty { margin-left: 64px; }
  .sub { color: var(--graphite); font-size: 13.5px; margin: 2px 0 10px; }

  /* ---- icons: currentColor, sized from the token scale ---- */
  .ic { display: inline-flex; width: 22px; height: 22px;
        vertical-align: -5px; flex: none; }
  .ic svg { width: 100%; height: 100%; display: block; }
  .ic.xs { width: 16px; height: 16px; vertical-align: -3px; }
  .btail { width: 20px; height: 20px; flex: none; }

  /* ---- actions written on the rules ---- */
  .row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .pick { flex: 1; min-width: 0; display: flex; align-items: center;
          gap: 9px; min-height: 44px; padding: 8px 12px;
          color: var(--graphite); background: var(--paper-raised);
          border: 1px dashed var(--rule-strong);
          border-radius: 10px 12px 10px 12px / 12px 10px 12px 10px;
          cursor: pointer; font-size: 14px; overflow: hidden; }
  .pick span:last-child { overflow: hidden; text-overflow: ellipsis;
                          white-space: nowrap; }
  #file { display: none; }
  input[type=password] { flex: 1; min-height: 44px; padding: 8px 10px;
          border: 1px solid var(--rule-strong); border-radius: 8px;
          background: var(--paper-raised); font-size: 14px;
          color: var(--ink-blue); }
  .btn { display: inline-flex; align-items: center; gap: 10px;
         min-height: 48px; padding: 8px 22px; cursor: pointer;
         font-family: var(--font-hand); font-size: 19px;
         color: var(--ink-blue); background: transparent;
         border: 1.5px solid var(--ink-blue);
         border-radius: var(--box-radius); }
  .btn:active { background: rgba(36, 65, 142, .07); }
  .btn:disabled { opacity: .4; cursor: default; }
  .btn.scanbtn { color: var(--cyan-wet); border-color: var(--cyan-wet); }
  .btn.scanbtn:active { background: rgba(0, 114, 163, .07); }
  .hidden { display: none !important; }
  .status { font-size: 14px; margin-top: 10px; white-space: pre-wrap;
            word-break: break-word; color: var(--ink-blue); min-height: 20px; }
  .status a { color: var(--ink-blue); }
  .status.err { color: var(--red-pen); }
  .status.err a { color: var(--red-pen); }

  /* ---- options drawer ---- */
  details.opts { margin-top: 12px; }
  details.opts summary { list-style: none; cursor: pointer; min-height: 44px;
          display: flex; align-items: center; gap: 8px;
          font-family: var(--font-hand); font-size: 16px;
          color: var(--graphite); }
  details.opts summary::-webkit-details-marker { display: none; }
  details.opts[open] summary { color: var(--ink-blue); }
  .opt { display: block; margin: 0 0 10px 8px; font-size: 13.5px;
         color: var(--graphite); }
  .opt .ic.xs { margin-right: 4px; }
  .opt input, .opt select { display: block; width: 100%; margin-top: 5px;
         padding: 8px 10px; min-height: 40px; font-size: 14px;
         border: 1px solid var(--rule-strong); border-radius: 8px;
         background: var(--paper-raised); color: var(--ink-blue); }
/* __CSS3__ */
"""
PAGE_CSS3 = """
  /* ---- the pencil progress (WEBDESIGN_PLAN §5) ---- */
  .working { margin: 10px 0 4px 6px; color: var(--cyan-wet); }
  .working svg { overflow: visible; display: block; }
  .pline { fill: none; stroke: currentColor; stroke-width: 2;
           stroke-linecap: round; stroke-dasharray: 140;
           stroke-dashoffset: 140;
           animation: write 1.6s ease-in-out infinite; }
  .pencilbody { animation: bob 0.8s ease-in-out infinite alternate; }
  @keyframes write {
    0% { stroke-dashoffset: 140; opacity: 1; }
    60% { stroke-dashoffset: 0; }
    85% { opacity: 1; }
    100% { stroke-dashoffset: 0; opacity: 0; }
  }
  @keyframes bob { from { transform: translateY(0); }
                   to { transform: translateY(1.5px); } }
  @media (prefers-reduced-motion: reduce) {
    .pline { animation: none; stroke-dashoffset: 0; opacity: .8; }
    .pencilbody { animation: none; }
  }

  /* ---- jobs: entries written ON the rules, marks in the margin ---- */
  .joblist { list-style: none; margin: 6px 0 0; padding: 0; }
  .job { display: grid; grid-template-columns: 52px minmax(0, 1fr);
         align-items: center; min-height: 46px; }
  .job .mark { display: flex; align-items: center; justify-content: center; }
  .job .mark .ic { width: 20px; height: 20px; }
  .jbody { display: flex; flex-wrap: wrap; align-items: baseline;
           gap: 2px 10px; padding: 8px 8px; min-width: 0; }
  .fmt { color: var(--graphite); width: 18px; height: 18px; }
  .fname { font-size: 14px; color: var(--ink-blue); overflow-wrap: anywhere; }
  .jid { font-family: var(--font-mono); font-size: 12.5px;
         color: var(--graphite); overflow-wrap: anywhere; }
  .jstate { font-family: var(--font-hand); font-size: 16.5px; }
  .errtext { flex-basis: 100%; font-size: 12.5px; color: var(--graphite); }
  .jcancel { margin-left: auto; width: 44px; height: 44px; padding: 0;
             display: inline-flex; align-items: center; justify-content:
             center; background: none; border: 0; cursor: pointer;
             color: var(--graphite); }
  .jcancel:active { color: var(--red-pen); }
  .empty { font-family: var(--font-hand); font-size: 16px;
           color: var(--graphite); }

  /* ---- the pens: one color per job state (WEBDESIGN_PLAN §2) ---- */
  .st-received, .st-queued { color: var(--graphite); }
  .st-converting, .st-scanning { color: var(--ink-blue); }
  .st-printing { color: var(--cyan-wet); }
  .st-done { color: var(--green-pen); }
  .st-failed { color: var(--red-pen); }
  .st-cancelled { color: var(--graphite); }
  .st-cancelled .jstate, .st-cancelled .fname {
    text-decoration: line-through; }

  /* ---- desktop: same sheet, wider margins (brief §6) ---- */
  @media (min-width: 768px) {
    .sheet { margin: 0 8vw 40px;
      background-image:
        linear-gradient(90deg, transparent 0 72px,
          var(--margin-red) 72px calc(72px + 2px),
          transparent calc(72px + 2px)),
        repeating-linear-gradient(to bottom,
          transparent 0 35px, var(--rule) 35px 36px);
    }
    section, .act { margin-left: 84px; }
    .jobs .rulehead, .empty { margin-left: 84px; }
    .job { grid-template-columns: 72px minmax(0, 1fr); }
    .act { max-width: 560px; }
    .joblist { columns: 2; column-gap: 30px; }
    .job { break-inside: avoid; }
  }
  /* ---- page nav: the always-visible Scan / Print hand-off ---- */
  .brandlink { display: flex; align-items: center; gap: 9px;
               text-decoration: none; color: inherit; }
  .topright { display: flex; align-items: center; gap: 12px; }
  .btn.nav { min-height: 44px; padding: 6px 16px; font-size: 17px; }

  /* ---- the login gate (LOGIN_PLAN §6): a third page, not a dialog ----
     Full-viewport takeover on the same paper — never a floating card
     (WEBDESIGN_PLAN: no cards, shadows, or boxed containers). */
  .gate { position: fixed; inset: 0; z-index: 40; background: var(--paper);
          overflow: auto; }
  .gate-remember { display: flex; align-items: center; gap: 9px;
                   margin: 2px 0 16px 8px; font-size: 14px;
                   color: var(--graphite); cursor: pointer; }
  .gate-remember input { width: 18px; height: 18px; flex: none;
                         accent-color: var(--ink-blue); }
</style>
</head>
<body>
__ICON_SPRITE__
"""
PAGE_BODY_HOME = """<header class="top">
  <div class="brand">
    <img src="/favicon.svg" alt="">
    <h1>printerService</h1>
  </div>
  <div class="topright">
    <a class="btn nav scanbtn" href="/scan"
       aria-label="Go to the scan page">Scan<svg class="btail"
      aria-hidden="true"><use href="#i-scan"/></svg></a>
    <span class="ic health" id="health" role="img"
          aria-label="checking server">
      <svg aria-hidden="true"><use href="#i-wifi-high"/></svg>
    </span>
  </div>
</header>
<main class="sheet">
  <section class="act">
    <h2 class="rulehead">Print</h2>
    <div class="row">
      <label class="pick" for="file">
        <span class="ic" aria-hidden="true"><svg><use href="#i-upload-simple"/></svg></span>
        <span id="pickName">Choose a PDF, image, Office, or text file…</span>
      </label>
      <input type="file" id="file"
             accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.txt,.csv">
    </div>
    <button id="printBtn" class="btn" onclick="sendPrint()">Print<svg
      class="btail" aria-hidden="true"><use href="#i-printer"/></svg></button>
    <button id="retryBtn" class="btn hidden" style="margin-left:10px"
            onclick="retryJob()">Retry failed job<svg class="btail"
      aria-hidden="true"><use href="#i-arrow-clockwise"/></svg></button>
    <div id="result" class="status" role="status"></div>
"""
PAGE_HTML2 = """    <details class="opts">
      <summary><span class="ic xs" aria-hidden="true"><svg><use
        href="#i-sliders-horizontal"/></svg></span>Print options</summary>
      <label class="opt"><span class="ic xs" aria-hidden="true"><svg><use
        href="#i-copy"/></svg></span>Copies
        <input type="number" id="copies" min="1" max="99" value="1">
      </label>
      <label class="opt"><span class="ic xs" aria-hidden="true"><svg><use
        href="#i-rows"/></svg></span>Pages
        <input type="text" id="pages" placeholder="all — or 1-3,5 or odd/even">
      </label>
      <label class="opt"><span class="ic xs" aria-hidden="true"><svg><use
        href="#i-printer"/></svg></span>Paper
        <select id="paper">
          <option value="">Printer default</option>
          <option value="a4">A4</option>
          <option value="letter">Letter (short bond)</option>
          <option value="long-bond">Long bond (8.5×13)</option>
          <option value="legal">Legal</option>
          <option value="a3">A3</option>
          <option value="a5">A5</option>
        </select>
      </label>
      <label class="opt"><span class="ic xs" aria-hidden="true"><svg><use
        href="#i-drop"/></svg></span>Color
        <select id="colorMode">
          <option value="color">Color</option>
          <option value="monochrome">Black &amp; white</option>
        </select>
      </label>
    </details>
  </section>

  <section class="jobs">
    <div class="jobshead" style="display:flex; align-items:center; gap:14px;">
      <h2 class="rulehead">Jobs</h2>
      <div class="working" id="jobsWorking" hidden aria-hidden="true" style="margin:0;">
        <svg viewBox="0 0 150 28" width="110" height="21">
          <path class="pline" d="M4 19 Q 14 7 24 19 T 44 19 T 64 19 T 84 19 T 104 19 T 124 19"/>
          <g class="pencilbody"><use href="#i-pencil" x="118" y="2" width="22" height="22"/></g>
        </svg>
      </div>
    </div>
    <p class="empty" id="jobsEmpty">Nothing here yet — send something to print.</p>
    <ul id="jobList" class="joblist"></ul>
  </section>
</main>
"""
PAGE_BODY_SCAN = """<header class="top">
  <div class="brand">
    <a class="brandlink" href="/" aria-label="Back to the print page">
      <img src="/favicon.svg" alt="">
      <h1>printerService</h1>
    </a>
  </div>
  <div class="topright">
    <a class="btn nav" href="/" aria-label="Back to the print page">Print<svg
      class="btail" aria-hidden="true"><use href="#i-printer"/></svg></a>
    <span class="ic health" id="health" role="img"
          aria-label="checking server">
      <svg aria-hidden="true"><use href="#i-wifi-high"/></svg>
    </span>
  </div>
</header>
<main class="sheet">
  <!-- The scan page (owner request: scan lives on its own page, reached
       from the always-visible Scan button on the print page). The page
       itself degrades calmly: until GET /scanners reports a scanner, the
       controls stay hidden and one status line says so. -->
  <div id="scanSection" class="act">
    <h2 class="rulehead">Scan</h2>
    <p class="sub" id="scanStatus">Checking for a scanner…</p>
    <div id="scanControls" style="display:none;">
      <p class="sub">Scanner: <span id="scanName"></span></p>
      <div class="row">
        <button id="scanBtn" class="btn scanbtn" onclick="startScan()">Scan<svg
        class="btail" aria-hidden="true"><use href="#i-scan"/></svg></button>
      <div class="working" id="scanWorking" hidden aria-hidden="true">
        <svg viewBox="0 0 150 28" width="132" height="25">
          <path class="pline" d="M4 19 Q 14 7 24 19 T 44 19 T 64 19 T 84 19 T 104 19 T 124 19"/>
          <g class="pencilbody"><use href="#i-pencil" x="118" y="2" width="22" height="22"/></g>
        </svg>
      </div>
      <details class="opts">
        <summary><span class="ic xs" aria-hidden="true"><svg><use
          href="#i-sliders-horizontal"/></svg></span>Scan options</summary>
        <label class="opt"><span class="ic xs" aria-hidden="true"><svg><use
          href="#i-crosshair"/></svg></span>Resolution
          <select id="scanDpi">
            <option value="150">150 dpi (faster)</option>
            <option value="200" selected>200 dpi</option>
            <option value="300">300 dpi (slower)</option>
          </select>
        </label>
        <label class="opt"><span class="ic xs" aria-hidden="true"><svg><use
          href="#i-drop"/></svg></span>Color
          <select id="scanColorMode">
            <option value="color" selected>Color</option>
            <option value="greyscale">Greyscale</option>
          </select>
        </label>
        <label class="opt"><span class="ic xs" aria-hidden="true"><svg><use
          href="#i-file-pdf"/></svg></span>Format
          <select id="scanFormat">
            <option value="pdf" selected>PDF (document)</option>
            <option value="png">PNG (image)</option>
            <option value="jpeg">JPEG (image)</option>
          </select>
        </label>
      </details>
    </div>
    <div id="scanResult" class="status" role="status"></div>
  </div>
</main>
"""

# The login gate (docs/LOGIN_PLAN.md §6) — shared by BOTH pages, a third
# page of the same notebook rather than a modal card. Hidden by default:
# JS reveals it only when /auth/status reports a PIN is required AND the
# stored session token is not currently valid. The ids are test-pinned
# hooks (same convention as startScan()/scanBtn).
GATE_HTML = """<div id="pinOverlay" class="gate hidden" role="dialog"
     aria-modal="true" aria-labelledby="gateTitle">
  <header class="top">
    <div class="brand">
      <img src="/favicon.svg" alt="">
      <h1>printerService</h1>
    </div>
    <span class="ic health" aria-hidden="true"><svg><use
      href="#i-lock-key"/></svg></span>
  </header>
  <main class="sheet">
    <section class="act">
      <h2 class="rulehead" id="gateTitle"><span class="ic"
        aria-hidden="true"><svg><use href="#i-lock-key"/></svg></span>
        Enter PIN</h2>
      <div class="row">
        <input type="password" id="pinInput" autocomplete="current-password"
               placeholder="PIN" aria-label="PIN">
      </div>
      <label class="gate-remember"><input type="checkbox" id="pinRemember"
        checked> Remember this device</label>
      <button class="btn" onclick="submitLogin()">Unlock</button>
      <div id="pinError" class="status err hidden" role="alert"></div>
    </section>
  </main>
</div>
"""

PAGE_JS1 = """
<script>
// ---- handles over the redesigned DOM (ids are pinned by tests) ----
const btn = document.getElementById("printBtn");
const resultDiv = document.getElementById("result");
const retryBtn = document.getElementById("retryBtn");
const jobList = document.getElementById("jobList");
const jobsEmpty = document.getElementById("jobsEmpty");
const jobsWorking = document.getElementById("jobsWorking");

// Client-side convenience only — the server re-checks everything
// (extension allowlist + magic bytes) and never trusts the browser.
const OK_TYPES = [
  ".pdf", ".jpg", ".jpeg", ".png", ".webp",
  ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
  ".odt", ".ods", ".odp",
  ".txt", ".csv",
];

let failedJobId = null;

function show(text, cls) {
  resultDiv.textContent = text;
  resultDiv.className = "status" + (cls ? " " + cls : "");
}

function retryControls(visible) {
  retryBtn.classList.toggle("hidden", !visible);
}

// Icon helper — names are static constants from STATE_ICON/fmtIcon below,
// NEVER server data, so innerHTML here is safe (the scan download link is
// the one other place innerHTML is used, built only from the server-issued
// job id).
function iconEl(name, cls) {
  const holder = document.createElement("span");
  holder.className = "ic" + (cls ? " " + cls : "");
  holder.setAttribute("aria-hidden", "true");
  holder.innerHTML = '<svg><use href="#i-' + name + '"/></svg>';
  return holder;
}

// Re-print a failed job from its stored upload (p14) — no re-upload
// needed. Resumes polling as if the job had just been queued.
async function retryJob() {
  if (!failedJobId) { return; }
  const headers = authHeaders();
  retryControls(false);
  show("Retrying job " + failedJobId + "…", "ok");
  try {
    const response = await fetch("/jobs/" + failedJobId + "/retry",
                                 { method: "POST", headers });
    const data = await response.json();
    if (response.ok) {
      poll(failedJobId, 0);
    } else if (response.status === 401) {
      sessionExpired();
    } else {
      show("Retry refused: " + (data.detail || response.status), "err");
    }
  } catch (networkError) {
    show("Could not reach the server. Are you on the same Wi-Fi?", "err");
  }
}

async function sendPrint() {
  const fileInput = document.getElementById("file");
  const file = fileInput.files[0];

  if (!file) { show("Pick a file first.", "err"); return; }
  if (!OK_TYPES.some(ext => file.name.toLowerCase().endsWith(ext))) {
    show("That file type isn't supported yet — PDF, images, Office "
         + "documents, or TXT/CSV.", "err");
    return;
  }

  // Basic client-side size check for instant feedback; the server enforces
  // the real limit (never trust the client — Section 8 of the docs).
  btn.disabled = true;
  show("Sending " + file.name + " (" +
       (file.size / 1e6).toFixed(1) + " MB)…");

  try {
    const body = new FormData();
    body.append("file", file);            // field name must be "file"

    // Print options (Phase 7) — all optional; empty fields mean defaults.
    body.append("copies", document.getElementById("copies").value || "1");
    body.append("pages", document.getElementById("pages").value.trim());
    body.append("paper", document.getElementById("paper").value);
    body.append("color_mode", document.getElementById("colorMode").value);

    // Credentials come from the login gate's stored session token
    // (authHeaders below); the server never trusts the browser anyway.
    const headers = authHeaders();

    const response = await fetch("/print", { method: "POST", body, headers });
    const data = await response.json();

    if (response.ok) {
      show("queued — job " + data.job_id + ", checking status…", "ok");
      poll(data.job_id, 0);
      loadJobs();
    } else if (response.status === 401) {
      sessionExpired();
    } else {
      // The server answered with a problem (415 not-a-PDF, 413 too big, …)
      show("Server said: " + (data.detail || response.status), "err");
    }
  } catch (networkError) {
    // fetch only throws on network-level failures: server down, Wi-Fi off,
    // firewall drop. This is the "silently hangs" case in Section 14.
    show("Could not reach the server. Are you on the same Wi-Fi?", "err");
  } finally {
    btn.disabled = false;
  }
}
"""
PAGE_JS2 = r"""
// Poll the job until it's done or failed — this is the "is my print
// finished yet?" loop the Section 11 API was designed for. Status lines
// lead with the API's exact state word (WEBDESIGN_PLAN §0).
async function poll(jobId, attempt) {
  if (attempt > 60) {  // ~2 minutes; spooler can be slow with big files
    show("Still not confirmed after 2 min. Check GET /jobs/" + jobId +
         " or the printer's queue.", "ok");
    return;
  }
  try {
    const response = await fetch("/jobs/" + jobId, { headers: authHeaders() });
    if (!response.ok) {
      show("Lost track of job " + jobId + " (HTTP " + response.status + ")",
           "err");
      return;
    }
    const job = await response.json();
    if (job.status === "done") {
      retryControls(false);
      show("done — printed to " + (job.printer || "printer") +
           ". job " + jobId, "ok");
      loadJobs();
      return;
    }
    if (job.status === "failed") {
      failedJobId = jobId;
      retryControls(true);
      show("failed — " + (job.error || "unknown reason") +
           ". You can retry it from the stored copy.", "err");
      loadJobs();
      return;
    }
    if (job.status === "cancelled") {
      retryControls(false);
      show("cancelled — job " + jobId, "err");
      loadJobs();
      return;
    }
    show("status: " + job.status, "ok");
    loadJobs();
    setTimeout(() => poll(jobId, attempt + 1), 2000);
  } catch (networkError) {
    // One dropped poll shouldn't end monitoring — keep trying.
    setTimeout(() => poll(jobId, attempt + 1), 3000);
  }
}

// ---- the Jobs list: entries written on the rules (WEBDESIGN_PLAN §6) ----
// One mark per state in the margin column; status is icon + exact word +
// pen color, never color alone.
const STATE_ICON = {
  received: "clock",
  queued: "clock",
  converting: "pencil",
  printing: "printer",
  done: "check-circle-fill",
  failed: "x-circle",
  cancelled: "prohibit",
};

// Which file-format glyph to show — from the server's detected category
// first, falling back to the stored filename's extension.
function fmtIcon(job) {
  const fmt = (job.format || "").toLowerCase();
  const name = (job.filename || "").toLowerCase();
  if (fmt.indexOf("csv") >= 0 || name.endsWith(".csv")) { return "file-csv"; }
  if (fmt.indexOf("image") >= 0 || /\.(jpg|jpeg|png|webp)$/.test(name)) {
    return "file-image";
  }
  if (/\.(xls|xlsx|ods)$/.test(name)) { return "file-xls"; }
  if (/\.(ppt|pptx|odp)$/.test(name)) { return "file-ppt"; }
  if (fmt.indexOf("office") >= 0 ||
      /\.(doc|docx|odt)$/.test(name)) { return "file-doc"; }
  if (fmt.indexOf("text") >= 0 || name.endsWith(".txt")) {
    return "file-txt";
  }
  return "file-pdf";
}

function isActive(status) {
  return status === "received" || status === "queued" ||
         status === "converting" || status === "printing";
}

function renderJobs(items) {
  jobList.textContent = "";
  jobsEmpty.style.display = items.length ? "none" : "";
  let anyActive = false;
  items.forEach(job => {
    if (isActive(job.status)) { anyActive = true; }
    const li = document.createElement("li");
    li.className = "job st-" + job.status;
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.appendChild(iconEl(STATE_ICON[job.status] || "clock"));
    const body = document.createElement("div");
    body.className = "jbody";
    body.appendChild(iconEl(fmtIcon(job), "fmt"));
    const name = document.createElement("span");
    name.className = "fname";
    name.textContent = job.filename || "(file)";
    body.appendChild(name);
    const id = document.createElement("span");
    id.className = "jid";
    id.textContent = job.job_id;
    body.appendChild(id);
    const state = document.createElement("span");
    state.className = "jstate";
    state.textContent = job.status;
    body.appendChild(state);
    if (job.error) {
      const err = document.createElement("span");
      err.className = "errtext";
      err.textContent = job.error;
      body.appendChild(err);
    }
    if (isActive(job.status)) {
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "jcancel";
      cancel.setAttribute("aria-label", "Cancel print job " + job.job_id);
      cancel.appendChild(iconEl("trash"));
      cancel.addEventListener("click", () => cancelJob(job.job_id));
      body.appendChild(cancel);
    }
    li.appendChild(mark);
    li.appendChild(body);
    jobList.appendChild(li);
  });
  // The pencil works while anything is queued/converting/printing.
  jobsWorking.hidden = !anyActive;
}

async function loadJobs() {
  try {
    const response = await fetch("/jobs");
    if (!response.ok) { return; }  // the list is best-effort, never noisy
    renderJobs(await response.json());
  } catch (networkError) {
    /* status list is best-effort; the page works without it */
  }
}

async function cancelJob(jobId) {
  const headers = authHeaders();
  try {
    const response = await fetch("/jobs/" + jobId,
                                 { method: "DELETE", headers });
    if (response.status === 401) {
      sessionExpired();
    } else if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      show("Cancel refused: " + (data.detail || response.status), "err");
    }
  } catch (networkError) {
    show("Could not reach the server. Are you on the same Wi-Fi?", "err");
  }
  loadJobs();
}

// ---- the login gate (docs/LOGIN_PLAN.md §3/§5) ----
// One shared block for both pages. The raw PIN is submitted exactly once,
// to POST /auth/login; from then on every request carries the opaque
// session token it returned — never the PIN, never persisted anywhere the
// server can see. "Remember this device" is purely a client-side storage
// choice: localStorage survives the browser, sessionStorage dies with it.
const TOKEN_KEY = "printerService.pinToken";

function storedToken() {
  return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
}

function saveToken(token, remember) {
  (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
}

// The single place every authed request builds its headers — replaces the
// old per-action "type the PIN again" field.
function authHeaders() {
  const token = storedToken();
  return token ? { "X-Session-Token": token } : {};
}

function showGate() {
  const overlay = document.getElementById("pinOverlay");
  if (!overlay) { return; }
  overlay.classList.remove("hidden");
  document.getElementById("pinError").classList.add("hidden");
  const input = document.getElementById("pinInput");
  input.value = "";
  input.focus();
}

function hideGate() {
  document.getElementById("pinOverlay").classList.add("hidden");
}

// A 401 from any protected route means the session died mid-action
// (server restarted since login) — raise the gate, not a dead-end error.
function sessionExpired() {
  clearToken();
  showGate();
}

// Focus is trapped while the gate is up: unlike every convenience
// overlay in this app, this one genuinely blocks use of the page.
document.addEventListener("keydown", function (event) {
  const overlay = document.getElementById("pinOverlay");
  if (!overlay || overlay.classList.contains("hidden")
      || event.key !== "Tab") { return; }
  const focusable = overlay.querySelectorAll("input, button");
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});

async function submitLogin() {
  const input = document.getElementById("pinInput");
  const error = document.getElementById("pinError");
  const pin = input.value.trim();
  if (!pin) { input.focus(); return; }
  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: pin }),
    });
    if (response.ok) {
      const data = await response.json();
      saveToken(data.token,
                document.getElementById("pinRemember").checked);
      hideGate();
    } else {
      // Error detail is real information: system font, --red-pen, never
      // the handwriting face (WEBDESIGN_PLAN §3). Stale tokens, if any,
      // are discarded; focus stays in the field.
      error.textContent = "Incorrect PIN.";
      error.classList.remove("hidden");
      clearToken();
      input.focus();
      input.select();
    }
  } catch (networkError) {
    error.textContent = "Could not reach the server. Are you on the same Wi-Fi?";
    error.classList.remove("hidden");
  }
}

// Phase 3 (LOGIN_PLAN §5 step 5): the initial check happens at load, and
// the same check runs on the health poll's 30 s cadence — so a server
// restart mid-session raises the gate on the next beat without a reload.
async function checkGate() {
  try {
    const response = await fetch("/auth/status", { headers: authHeaders() });
    const info = await response.json();
    if (info.pin_required && info.session_valid !== true) {
      sessionExpired();
    }
  } catch (networkError) {
    /* server unreachable — the header wifi icon already says so */
  }
}
"""
PAGE_JS3 = """
// ---- Scan page (owner request: scan lives on its own page at GET /scan,
// reached from the always-visible Scan button on the print page). Everything
// here exists only on that page — the guard below keeps the print page free
// of scan code paths. On a scanner-less setup the page degrades to one calm
// status line; detection failure never breaks anything, hence the catches.
if (document.getElementById("scanSection")) {
  const scanBtn = document.getElementById("scanBtn");
  const scanResult = document.getElementById("scanResult");
  const scanWorking = document.getElementById("scanWorking");
  const scanControls = document.getElementById("scanControls");
  const scanStatus = document.getElementById("scanStatus");
  let scanInFlight = false;

  function scanShow(text, cls) {
    scanResult.textContent = text;
    scanResult.className = "status" + (cls ? " " + cls : "");
  }

  // Every terminal path of a scan (done/failed/cancelled/lost/timeout) ends
  // here: release the button and put the pencil away.
  function scanSettle() {
    scanInFlight = false;
    scanBtn.disabled = false;
    scanWorking.hidden = true;
  }

  // Ask the server ONCE whether this printer setup can scan at all.
  // No scanner (or the feature disabled) → controls never appear and one
  // line explains why; otherwise they're revealed.
  (async function checkScanner() {
    try {
      const response = await fetch("/scanners");
      if (!response.ok) {
        scanStatus.textContent = "Could not check for a scanner.";
        return;
      }
      const info = await response.json();
      if (!info.available || !info.devices.length) {
        scanStatus.textContent =
          "No scanner detected — the printer may be off or unplugged.";
        return;
      }
      scanStatus.textContent = "";
      scanControls.style.display = "block";
      document.getElementById("scanName").textContent =
        info.devices[0].name || "scanner";
    } catch (e) {
      scanStatus.textContent = "Could not check for a scanner.";
    }
  })();

  // The Scan button: POST /scan, then poll the job the same way print does.
  // The button stays disabled while a scan is in flight — the flatbed can
  // only do one page at a time, so a second tap would just hit a busy
  // scanner (WIA_ERROR_BUSY) instead of queueing usefully.
  async function startScan() {
    if (scanInFlight) { return; }
    scanInFlight = true;
    scanBtn.disabled = true;
    scanWorking.hidden = false;
    scanShow("Starting scan…", "ok");
    const headers = authHeaders();
    // Scan options (Phase 4): DPI, color mode, output format — strictly
    // allowlisted server-side; the selects only ever offer valid values.
    const body = new FormData();
    body.append("dpi", document.getElementById("scanDpi").value);
    body.append("color_mode", document.getElementById("scanColorMode").value);
    body.append("format", document.getElementById("scanFormat").value);
    try {
      const response = await fetch("/scan", { method: "POST", headers, body });
      const data = await response.json();
      if (response.ok) {
        scanShow("queued — the flatbed is working. Checking status…", "ok");
        pollScan(data.job_id, 0);
      } else if (response.status === 401) {
        scanSettle();
        sessionExpired();
      } else {
        scanSettle();
        scanShow("Server said: " + (data.detail || response.status), "err");
      }
    } catch (networkError) {
      scanSettle();
      scanShow("Could not reach the server. Are you on the same Wi-Fi?", "err");
    }
  }

  // Poll a scan job until it's done — mirrors print's poll() (SCAN_PLAN §6
  // is explicit: reuse the existing polling pattern, don't invent a new one).
  async function pollScan(jobId, attempt) {
    if (attempt > 75) {  // ~2.5 min; scans take 40-60 s (spike S2) + print load
      scanSettle();
      scanShow("Still not confirmed after ~2.5 min. Check /scan/jobs/" + jobId +
               " for the current status.", "ok");
      return;
    }
    try {
      const response = await fetch("/scan/jobs/" + jobId,
                                   { headers: authHeaders() });
      if (!response.ok) {
        scanSettle();
        scanShow("Lost track of scan job " + jobId + " (HTTP " +
                 response.status + ")", "err");
        return;
      }
      const job = await response.json();
      if (job.status === "done") {
        scanSettle();
        // The link is built from the server-issued job id (a UUID hex) —
        // nothing from the server goes into innerHTML, and the download
        // endpoint is the only thing it ever points at.
        scanResult.className = "status";
        scanResult.innerHTML = "done — Scan ready: " +
          '<a href="/scan/jobs/' + jobId + '/download">View / Download</a>' +
          " (job " + jobId + ")";
        return;
      }
      if (job.status === "failed") {
        scanSettle();
        scanShow("failed — " + (job.error || "unknown reason"), "err");
        return;
      }
      if (job.status === "cancelled") {
        scanSettle();
        scanShow("cancelled — scan job " + jobId, "err");
        return;
      }
      scanShow("status: " + job.status, "ok");
      setTimeout(() => pollScan(jobId, attempt + 1), 2000);
    } catch (networkError) {
      // One dropped poll shouldn't end monitoring — keep trying.
      setTimeout(() => pollScan(jobId, attempt + 1), 3000);
    }
  }

  // Inline onclick handlers resolve against window — expose the two
  // functions the scan page's HTML references ("startScan()", pollScan).
  window.startScan = startScan;
  window.pollScan = pollScan;
}

// ---- server health: the header wifi icon is the reachability check ----
async function checkHealth() {
  const el = document.getElementById("health");
  const use = el.querySelector("use");
  try {
    const response = await fetch("/health");
    el.className = "ic health " + (response.ok ? "up" : "down");
    use.setAttribute("href",
                     response.ok ? "#i-wifi-high" : "#i-wifi-slash");
    el.setAttribute("aria-label",
                    response.ok ? "server reachable" : "server unreachable");
  } catch (networkError) {
    el.className = "ic health down";
    use.setAttribute("href", "#i-wifi-slash");
    el.setAttribute("aria-label", "server unreachable");
  }
}

// ---- file picker label + startup ----
const fileInput = document.getElementById("file");
if (fileInput) {
  fileInput.addEventListener("change", function () {
    const picked = this.files[0];
    document.getElementById("pickName").textContent =
      picked ? picked.name : "Choose a PDF, image, Office, or text file…";
  });
}

checkHealth();   // the header wifi icon exists on both pages
checkGate();     // the login gate: on load, and again on the health
setInterval(checkGate, 30000);   // poll's cadence (LOGIN_PLAN §5 step 5)
if (document.getElementById("jobList")) {   // the print page only
  loadJobs();
  setInterval(loadJobs, 5000);  // cheap on a LAN; keeps the sheet fresh
}
setInterval(checkHealth, 30000);
</script>
</body>
</html>"""
# The two pages are assembled once at import: asset placeholders become the
# inlined font and the icon sprite (both degrading to nothing if the
# committed files are missing), and the shared login-gate markup is added
# to both — hidden by default, revealed by /auth/status-driven JS only.
PAGE = (
    PAGE_CSS1 + PAGE_CSS2 + PAGE_CSS3 + GATE_HTML + PAGE_BODY_HOME
    + PAGE_HTML2 + PAGE_JS1 + PAGE_JS2 + PAGE_JS3
)
SCAN_PAGE = (
    PAGE_CSS1 + PAGE_CSS2 + PAGE_CSS3 + GATE_HTML + PAGE_BODY_SCAN
    + PAGE_JS1 + PAGE_JS2 + PAGE_JS3
)
for _page_name, _page in (("PAGE", PAGE), ("SCAN_PAGE", SCAN_PAGE)):
    _page = _page.replace("__FONT_DATA_URI__", _font_data_uri())
    _page = _page.replace("__ICON_SPRITE__", _icon_sprite())
    if _page_name == "PAGE":
        PAGE = _page
    else:
        SCAN_PAGE = _page


@router.get("/", response_class=HTMLResponse)
def index():
    """Serve the upload page. Opening the server's URL on the phone IS the app."""
    return PAGE


@router.get("/scan", response_class=HTMLResponse)
def scan_page():
    """Serve the scan page — the print page's counterpart, reached from the
    always-visible Scan button on /. Same sheet, same rules; the page degrades
    to a calm 'no scanner' line when the hardware isn't there."""
    return SCAN_PAGE


@router.get("/favicon.svg", include_in_schema=False)
@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve the SVG icon for browser tabs."""
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")







