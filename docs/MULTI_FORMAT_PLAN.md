# Multi-Format Printing — Investigation, Decision Record & Roadmap

Status: **approved plan** (branch `multiple-types-compatibility`).
Goal: grow the PDF-only MVP into a general multi-format network printing
service while keeping it simple enough for a beginner home lab on an
old/low-spec Windows PC.

Claims are tagged like SOURCE_OF_TRUTH:
🟢 CONFIRMED FACT · 🔵 RECOMMENDED (decided here) · 🟡 ALTERNATIVE · 🔴 NEEDS TESTING (spike) · ⚪ FUTURE

---

## 0. Where this stage stopped (updated 2026-08-29)

**Code: complete through Phase 4. Paper verification: images ✓, text/CSV ✓, office pending (needs LibreOffice).**

- 🟢 **Done and committed** on `multiple-types-compatibility` (pushed;
  PR #1 open, CI running): `56afce6` (this roadmap) → `d078d41` **p10**
  groundwork (detection + processor registry + generalized uploads +
  conversion lock) → `b928e11` **p11** images → `19a7223` **p12** office →
  `0be3eab` **p13** text/CSV → `5527c7c` docs → `1f1a1f4` spike fix. All
  four MVP categories are registered; 193 automated tests pass at ≈97 %
  coverage (gate 90 %); ruff clean.
- ✅ **Spikes T5 (images) and T7 (TXT/CSV) PASSED on real paper**
  (2026-08-29; details in SOURCE_OF_TRUTH §5). The T5 `--paper A4` copy
  confirmed the Epson driver honors `-print-settings`, so `PAPER_SIZE`
  may now be set in `.env` (optional; empty = driver chooses).
- 🔴 **The last open MVP gate is T6 (office):** install LibreOffice on the
  print-server PC, run `spike_t6_office.py`, judge the paper (table fits,
  only the print area prints in landscape, 16:9 slides landscape), record
  results in SOURCE_OF_TRUTH §5. Until then office uploads keep getting
  the kill-switch 415 — designed behavior.
- ⚪ **Phases 5–7 are NOT started** — §10 below describes them as designed
  (queue management, reliability, print options UI), not as built.
- Housekeeping: CI runs on PR #1; merge when green.

---

## 1. Executive summary — the 10 answers

| # | Question | Decision |
|---|----------|----------|
| 1 | Keep SumatraPDF? | **Yes** — unchanged CLI, same install, same `submit_pdf()` |
| 2 | Replace it? | **No** |
| 3 | What joins it? | LibreOffice Headless (office→PDF converter only), Pillow (images), reportlab (TXT/CSV) — all free (MPL-2.0 / MIT-style / BSD) |
| 4 | Convert to PDF before printing? | **Yes**, for every non-PDF input |
| 5 | Internal print format? | **PDF**, stored beside the original upload |
| 6 | Python's role? | Orchestrator: Pillow/reportlab/pywin32 as libraries; LibreOffice/SumatraPDF as external executables via arg-list subprocess |
| 7 | First new formats? | Images (JPG/PNG/WebP) — no heavy dependencies |
| 8 | Architecture? | Format processors → common PDF → existing `submit_pdf()` print engine, inserted at one point of the current pipeline |
| 9 | Avoid? | Per-format direct printing, MS Office COM, RAW/GDI printing, anything beyond SQLite, internet exposure (SOURCE_OF_TRUTH §16) |
| 10 | Implement first? | Hardware spike T5–T7 on the real PC, then the Phase 1 refactor (p10) |

---

## 2. What the service is today 🟢 (verified by reading the code)

- FastAPI console app (`uvicorn app.main:app`), optional PIN auth, LAN-only
  (private-profile firewall rule), Epson L3210 on USB via the Windows queue
  `EPSON L3210 Series`.
- `POST /print` → `validate_pdf()` (`.pdf` extension + `%PDF-` magic +
  `MAX_UPLOAD_MB`) → saved as `uploads/<job_id>.pdf` → in-memory job store
  (dict behind a lock, SOURCE_OF_TRUTH §12) → one daemon thread per job →
  `submit_pdf()` → `SumatraPDF.exe -print-to "<printer>" -silent <file>`
  (180 s timeout) → done → file deleted.
- The Windows "print" verb fallback is broken on this machine (spike T3,
  WinError 1155) and stays a documented safety net only.
- Spike T4 physically printed paper through the whole chain.
- 81 tests mock `win32print`; CI runs ruff + pytest + ≥90 % coverage.

**Key insight:** the service is already ~80 % format-agnostic.
`submit_pdf(pdf_path)` *is* the print-engine contract (PDF in → paper out).
The only PDF-specific code: `uploads.py` (validate/save/sweep), `config.py`
(`PDF_MAGIC`), `api/print.py` (415 message), `api/web.py` (`accept=".pdf"`).

## 3. Keep / modify / new / replace / isolate 🔵

- **Keep unchanged:** FastAPI app + routes + PIN auth; job store and lock;
  **`submit_pdf()` untouched**; logging; startup sweep pattern; tests/CI
  conventions; SumatraPDF itself.
- **Modify (surgical):** `uploads.py` (generic validation, real extension,
  sweep everything), `config.py` (format-related settings), `pipeline.py`
  (detect → processor → submit; real `converting`/`printing` states;
  conversion lock), `models/printing.py` (+`converting`, +`format` field),
  `api/print.py` + `api/web.py` (generic messages, wider accept list).
- **New:** `app/detection.py` (magic-byte-first detection);
  `app/processors/` package (`base.py` Processor protocol, `pdf.py`
  pass-through, later `images.py`, `office.py`, `text.py`).
- **Replaced:** nothing — no working component is rewritten.
- **Isolated behind interfaces:** (1) the Processor protocol
  (`process(src, out_dir) -> Path` returning a print-ready PDF); (2)
  `submit_pdf()`'s signature (a future alternative engine implements the
  same one call); (3) the job-store function set (dict → SQLite swap).

## 4. SumatraPDF evaluation — KEEP 🟢/🔵

🟢 Confirmed from the official CLI docs: `-print-to` / `-print-settings`
accept `paper=A4|letter|legal|...`, `fit`/`shrink`/`noscale`, `center`,
`color`/`monochrome`, `duplex`, copies (`3x`, `collate`), page ranges
(`2-6`, `odd`, `even`); documented exit codes 0/2/3/4/5/6 (2 = file won't
open, 4 = printer not found, 5 = driver/device failure) → mappable to human
messages. Reads PDF, EPUB, MOBI, CBZ, CBR, FB2, CHM, XPS, DjVu — **not
images, not office docs** — which is irrelevant here because processors
normalize everything to PDF first. (A)GPLv3 is unproblematic: invoked as a
separate process, no linking. ~15 MB, fast startup, actively maintained,
works from a console/Task-Scheduler session (the current deployment model).

### Alternatives rejected 🔵

| Alternative | Why rejected |
|---|---|
| LibreOffice `--pt` direct print | Still loads the whole office suite; bypasses the PDF quality checkpoint; weaker per-file error reporting |
| win32print RAW | The L3210 is a host-based GDI inkjet — RAW PDF bytes print as garbage |
| pypdfium2 → bitmap → GDI | Most control, most code, worse raster quality; documented future fallback |
| Ghostscript (mswinpr2) | AGPL, no advantage over Sumatra |
| Adobe/Foxit CLIs | Licensing / deprecation |
| MS Office COM, docx2pdf, docto | Need Office installed + licensed; unsupported headless; fragile |
| Windows print verb | Proven broken here (spike T3, WinError 1155) |

## 5. PDF as the intermediate format — YES 🔵

**Advantages:** one print engine; a debuggable artifact when paper looks
wrong (open `uploads/<id>.pdf`); all paper/fit/orientation handling in one
place (`-print-settings`); source-document layout fidelity preserved by
LibreOffice's own layout engine; JPEGs embed losslessly; testable without a
printer; one set of print options works for every format (Phase 7).
**Disadvantages:** extra disk I/O; 10–30 s conversion per office doc on an
old PC; exotic office features may not survive export; LibreOffice must be
installed. Alternatives (XPS, raster, "each format prints itself") are
worse: weaker tooling, no multipage, N engines = N failure modes.

## 6. Format strategy table 🔵

| Format | Processor | Convert to PDF? | Dependencies | Difficulty | Reliability | Notes |
|---|---|---|---|---|---|---|
| PDF | pass-through | — | none | trivial | high | today's behavior |
| JPG/JPEG | images (Pillow) | yes | Pillow | easy | high | EXIF rotation honored |
| PNG | images (Pillow) | yes | Pillow | easy | high | alpha → white |
| WebP | images (Pillow) | yes | Pillow | easy | high | wheels bundle libwebp |
| BMP/GIF/TIFF | images (bonus) | yes | Pillow | free | high | multipage TIFF |
| DOC/DOCX | office (LibreOffice headless) | yes | LibreOffice | medium | med-high | server-side fonts matter |
| XLS/XLSX | office (LibreOffice headless) | yes | LibreOffice | medium | medium | honors stored print areas/scaling |
| PPT/PPTX | office (LibreOffice headless) | yes | LibreOffice | medium | med-high | 1 slide = 1 page |
| ODT/ODS/ODP | office (bonus) | yes | LibreOffice | free | high | comes free with LibreOffice |
| TXT | text (reportlab) | generated | reportlab | easy | high | monospace, word-wrap, page breaks |
| CSV | text (csv + reportlab) | generated | reportlab | easy-med | high | bordered grid, capped rows/cols |

Policy rejections: `.docm/.xlsm/.pptm/.dotm` (macro-enabled), `.heic`
(needs pillow-heif — ⚪ v2), everything else not listed.

**Old-PC load profile (during a print job only — the service idles at
~100 MB):** PDF/Sumatra ~100 MB for 1–2 s; image conversion 50–200 MB for
<1 s; text conversion ~50 MB for <1 s; LibreOffice 300–500 MB for 5–30 s,
then the process exits and frees everything. Only LibreOffice is a real
cost, and there is no lighter alternative — any DOCX printer must load a
layout engine.

**Office kill switch:** office formats are printable only when
`ENABLE_OFFICE=1` (default) *and* LibreOffice is actually found.
Otherwise office uploads get a friendly 415 ("convert to PDF first");
PDF/images/text keep working. No uninstall needed to disable office.

## 7. Print-quality reality check (honest caveats) 🔵

- **DOCX — fonts are risk #1.** LibreOffice renders with fonts installed on
  the *server*; missing fonts get substituted and line breaks shift.
  Mitigation: install a reasonable font pack on the server; document it.
- **XLSX is the least predictable format** regardless of tool: sheets saved
  without a print area paginate all columns; wide sheets split arbitrarily.
  LibreOffice honors stored print areas/scaling/orientation. Document "set
  a print area in Excel for best results"; fit-to-width is a ⚪ v2 knob.
- **PPTX** is reliable: slide size becomes page size; 16:9 decks print
  landscape. Speaker notes are not printed.
- **Images:** honor EXIF orientation, alpha → white, fit-to-page centered
  with configurable margin, auto-landscape for wide images, downscale to
  ≤300 effective DPI.
- **PDF pass-through** is untouched; `paper=A4,fit` handles odd sizes.

## 8. Print job lifecycle 🔵

States: `received → queued → converting → printing → done | failed |
cancelled` (`printing` finally gets set; `converting` explains slow office
jobs to the phone).

1. `POST /print` → validate (extension allowlist → magic bytes → size cap →
   category availability) → save as `uploads/<job_id>.<ext>` → create job
   (format recorded) → **201 immediately**.
2. Worker thread: detect category → pick processor → status `converting` →
   produce `uploads/<job_id>.pdf` (conversions serialized by a lock —
   the old-PC guard).
3. Status `printing` → `submit_pdf(pdf_path)`.
4. done → delete original + intermediate; failed → keep both + human
   error; startup sweep clears leftovers.

Edge cases: printer offline → Sumatra exit 4/5 → FAILED with mapped
message (spooler-side stalls after acceptance can't be seen via exit code —
Phase 5 adds a pywin32 pre-check + retry). Conversion crash → timeout +
`taskkill /T`, FAILED with stderr tail. Corrupted file → passes magic,
fails converter → FAILED with converter error. Two users at once →
thread-per-job stays; one conversion lock serializes conversions; the
spooler serializes printing. Huge file → size cap + conversion timeout;
phone already got its 201. Restart mid-job → in-memory history lost
(accepted trade-off); sweep clears partials; Phase 5 adds SQLite +
startup recovery.

## 9. Security (practical, layered) 🔵

Keep: PIN + LAN-only + private-profile firewall; magic-byte validation
(generalized); **server-generated filenames** (client filename stored for
display only — kills path traversal); arg-list subprocess (never
`shell=True`); startup sweep.
Add: hard-reject macro formats; LibreOffice invoked as
`--headless --norestore --nolockcheck -env:UserInstallation=<private
profile>` (isolated profile, no network) with timeout + process-tree kill;
pinned dependencies.
Explicitly NOT in MVP: dedicated low-priv conversion account, sandboxing,
AV scanning — ⚪ v2+ options.

## 10. Phased roadmap

- **Phase 0 — hardware spike (real PC, real paper):** T5/T6/T7 below.
- **Phase 1 (p10) — refactor PDF pipeline, no behavior change:**
  detection + Processor layer + generalized uploads + conversion lock +
  `converting`/`printing` states; all tests stay green.
- **Phase 2 (p11) — images:** Pillow processor; web page accept/copy;
  `PAPER_SIZE` wiring (default empty = driver chooses, per the de-risking
  decision); cancel cleanup must delete `<job_id>.<ext>` too
  (`uploads.delete_job_files`). Code landed in p11 — physical check pending
  T5 (`spike_t5_images.py`), which is this phase's acceptance gate.
- **Phase 3 (p12) — office:** install LibreOffice (run T6 first);
  `office.py` adapter (timeout, taskkill, profile isolation,
  `ENABLE_OFFICE` kill switch); friendly error mapping; font-pack docs;
  verify a table-heavy DOCX and a print-area XLSX on real paper.
  Code landed in p12 (fresh throwaway profile per conversion instead of a
  shared one — crash-proof, ~1 s warmup cost). Physical check pending T6
  (`spike_t6_office.py`, needs `pip install python-docx openpyxl
  python-pptx` spike-only) — this phase's acceptance gate.
- **Phase 4 (p13) — text/CSV:** reportlab renderer — TXT = monospace text
  with wrap; CSV = bordered grid with row/col caps + "truncated" notice.
  Code landed in p13 (all four MVP categories now registered). Physical
  check pending T7 (`spike_t7_text.py`) — with T5/T6 this completes the
  MVP's paper verification.
- **Phase 5 (p14) — queue management:** cancel while queued/converting;
  spooler purge via `win32print.SetJob` once printed; retry failed jobs;
  SQLite persistence (SOURCE_OF_TRUTH §12 upgrade path) + startup recovery.
- **Phase 6 (p15) — reliability:** pre-dispatch printer-status check; error
  catalog (exit code → message); log rotation; startup recovery.
- **Phase 7 (v2) — print options & dialog UI:** optional per-request
  options on `POST /print`: `copies` (1–99 → `3x` + `collate`), `pages`
  (range `2-6`, `odd`/`even` — strict allowlist regex before it touches a
  command line), `paper` (A4 / short bond Letter / long bond 8.5×13 via
  `paper=215.9mm x 330.2mm` or driver paper name — one spike line), 
  `color_mode` (`color`/`monochrome`). One `print-settings` builder in the
  pipeline; stored on the job; web page gains dropdown/inputs in its
  vanilla-JS style. Works for **all** formats automatically because
  everything is a PDF by print time. Duplex/quality/tray hidden (L3210 has
  no duplex hardware, one tray). A print preview (serve the intermediate
  PDF to the phone before printing) comes nearly free later.

Each phase: ruff + pytest + ≥90 % coverage gate; README +
SOURCE_OF_TRUTH updated; one commit per phase (p10, p11, …).

## 11. MVP / v2 / future

- **MVP (Phases 0–4):** PDF, JPG/PNG/WebP, DOCX/XLSX/PPTX (+ legacy + ODF),
  TXT/CSV.
- **v2 (Phases 5–7):** queue management, reliability hardening, print
  options & dialog UI; plus HEIC via pillow-heif, pypdf pre-validation,
  multi-image jobs, printer-offline retry parking, per-format size caps,
  print preview.
- **Future (do NOT build):** everything in SOURCE_OF_TRUTH §16 (internet
  exposure, cloud, Docker, multi-user, dashboards), an IPP server, direct
  USB/Epson protocol, distributed anything.

## 12. Printer note

Stay on the Windows printing stack: SumatraPDF → spooler → Epson driver →
USB, exactly as today. Direct USB communication (ESC/P-R via libusb) only
pays off for real-time status/ink management and is a large, brittle,
printer-firmware-coupled build — rejected.

## 13. Assumptions that need the spike 🔴

1. LibreOffice headless behaves under the Task-Scheduler startup session on
   the target PC (T6).
2. The target OS runs current LibreOffice — ≤4 GB RAM is fine; if it turns
   out to be Win 7/8.1, pin LibreOffice 7.6.x (last branch supporting it).
3. The Epson driver honors `paper=A4` from Sumatra's `-print-settings`
   (today nothing pins paper size).
4. LibreOffice fidelity on *your* real documents (table-heavy DOCX,
   print-area XLSX).
5. ~1.2 GB free disk for LibreOffice; serialized conversions keep RAM safe
   on the ≤4 GB PC.
6. Long-bond paper (8.5×13) prints correctly via Sumatra custom paper size
   or the Epson driver's named paper (Phase 7 spike line).

## 14. Spike protocol (Phase 0)

Extend the T1–T4 convention in `spike_print_test.py` (T4 = SumatraPDF chain,
PASS with real paper). Same output style: print `T<n> PASS/FAIL` plus
timings, and record results in SOURCE_OF_TRUTH §5.

### T5 — Images → PDF → paper
1. `pip install pillow` (dev only for the spike).
2. Python: create three test images with Pillow (a photo-like gradient JPEG,
   a PNG with transparency, a WebP), then fit each onto an A4/Letter page
   (white background, centered) and save as PDF.
3. Print each via the T4 command (`SumatraPDF.exe -print-to "EPSON L3210
   Series" -silent <file.pdf>`).
**PASS =** three pages on paper, correct orientation, transparency rendered
white (not black), no clipping.

### T6 — Office → PDF → paper (needs LibreOffice installed)
1. Install LibreOffice (default install; note the disk usage).
2. `soffice --headless --norestore --convert-to pdf --outdir %TEMP% test.docx`
   with (a) a table-heavy DOCX, (b) an XLSX with a defined print area, (c) a
   16:9 PPTX. Open each PDF and compare against the source app.
3. Print each PDF via the T4 command.
4. Measure: `powershell Measure-Command { soffice ... }` per file; watch RAM
   in Task Manager during conversion.
5. Repeat one conversion while the service runs under Task Scheduler
   ("at startup", before logon) to verify session-0 behavior.
**PASS =** PDFs open correctly, layouts acceptable, paper output matches,
conversion ≤ 30 s and RAM ≤ ~500 MB on the target PC.

### T7 — TXT/CSV → PDF → paper
1. `pip install reportlab` (dev only for the spike).
2. Python: render a wrapped TXT (long lines, unicode) and a CSV (20×6 grid)
   to PDF with reportlab; print via T4.
**PASS =** readable monospace text with wrapping; CSV grid aligned, nothing
cut off at the right margin.

## 15. Open items

- [x] Phase 1 refactor (p10), images (p11), office (p12), text/CSV (p13) —
      code committed and pushed.
- [x] Branch pushed; CI runs on PR #1 — merge when green.
- [x] T5 images spike PASSED on real paper (2026-08-29), including the
      `paper=A4` driver check.
- [x] T7 text/CSV spike PASSED on real paper (2026-08-29).
- [ ] **T6 office spike** — install LibreOffice first; the last open gate
      of the multi-format MVP.
- [ ] Set `PAPER_SIZE=A4` in `.env` whenever desired (verified by T5;
      optional — empty = driver chooses).
- [ ] Confirm the target PC's Windows version before enabling office
      (pin LibreOffice 7.6.x if it's Win 7/8.1).
- [ ] Phase 7: verify long-bond paper (8.5×13) on the Epson driver
      (custom mm size vs driver paper name).
