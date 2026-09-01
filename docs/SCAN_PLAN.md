# Scan Feature — Feasibility, Decision Record & Roadmap

Status: **approved plan, compatibility-reviewed (§0); Phase 0 COMPLETE —
S1/S2/S3/S4 all PASS on the real L3210 (2026-09-01), including the
unplugged clean-degradation proof. Phase 1 (detection) and Phase 2
(basic scan pipeline: POST /scan + status/download/cancel + downloads/)
LANDED. Next: Phase 3 (web UI). Branch `scan-feature`.**
Goal: add an optional **scan** capability (Android → Python service →
Windows → USB → printer's scanner glass → back to phone) to the existing
print service, **without ever affecting printing** on a printer that has
no scanner, and with **zero new required dependencies**.

Claims are tagged like SOURCE_OF_TRUTH / MULTI_FORMAT_PLAN:
🟢 CONFIRMED FACT · 🔵 RECOMMENDED (decided here) · 🟡 ALTERNATIVE ·
🔴 NEEDS TESTING (spike) · ⚪ FUTURE

---

## 0. Compatibility review (2026-09-01) 🟢

The plan was checked line-by-line against the code before approval. Result:
**compatible — green light.** Verified claims:

- `pywin32` is already a runtime dependency (`requirements.txt`,
  `sys_platform == "win32"` marker) → `win32com.client` needs no new install.
- Pillow is already in (`pillow>=10.3`) and `app/processors/images.py` has
  exactly the reusable fit-to-page logic (`layout()`, `page_size_pt()`, or
  simply `ImageProcessor.process()` — the real production path, which is what
  the spike uses, the same way T7 used the real `TextProcessor`).
- The lazy-import trick is real (`app/printer/windows.py` imports
  `win32print` inside every function) and the test-side mirror exists
  (`tests/conftest.py` injects a fake module into `sys.modules`) → the same
  pattern works for a fake `win32com` on the Ubuntu CI runner.
- The `ENABLE_OFFICE` kill switch in `app/config.py` is the exact template
  for `ENABLE_SCAN`.
- `main.py` mounts routers with plain `include_router` and its lifespan does
  sweep + recovery — a scan router and a `downloads/` sweep slot in additively.
- `PrintJob`/`JobStatus` and the print `jobs` SQLite schema are genuinely
  print-shaped — the separate-scan-store decision (§4) is confirmed correct.

Four adjustments were made to this document during review (all resolved here,
so the body below is already corrected):

1. **WIA constants:** `win32com.client.constants` needs a makepy-generated
   module, so the code passes WIA's format GUIDs directly (§2).
2. **Status codes** follow the codebase's existing conventions — 503 for an
   unavailable capability (mirrors `/printers`), 201 for an accepted job
   (mirrors `/print`) — not the generic 404/409/202 first proposed (§4, §5).
3. **PIN scope** follows `app/services/auth.py`: state-changing routes are
   pinned, read-only GETs stay open (§7).
4. **Scan job storage** is pinned down: a separate `scan_jobs` table in the
   same SQLite file, in a new module with its own connection + lock — never
   touching `jobs.py`'s shared connection (§4).

---

## 1. Executive summary — the 6 answers

| # | Question | Decision |
|---|----------|----------|
| 1 | Is scanning possible at all? | **Yes** — the L3210 is a flatbed all-in-one, and Windows exposes scanners over a COM API (WIA) already reachable through `pywin32`, a dependency you have. |
| 2 | New required dependency? | **None.** `win32com.client` ships inside `pywin32`. Optional: reuse `Pillow` (already added in p11) to wrap the scanned image into a PDF. |
| 3 | How do we detect "does this printer have a scanner"? | Enumerate Windows' WIA device list at startup/on-demand; a printer with no scanner (or a machine with WIA unavailable) simply returns an empty list — never an error, never a crash. |
| 4 | Does this touch the print code path? | **No.** New files only (`app/scanner/`), new routes only, one additive block in `main.py`. `app/printer/windows.py` and the whole print pipeline stay byte-for-byte unchanged. |
| 5 | What if there's no scanner? | The `/scanners` endpoint returns `[]`, the web page's Scan section simply doesn't render, and `/print`, `/jobs`, `/health` behave exactly as they do today. This is a hard design constraint, not just a hope. |
| 6 | Output format? | **PDF by default** (consistent with the print side's "one internal format"), with an optional `?format=png` escape hatch for a raw image. |

---

## 2. Is it physically/technically possible? 🟢

**Hardware:** the Epson L3210 is not print-only — it's an EcoTank
**all-in-one** with a flatbed CIS scanner (optical resolution up to
1200×2400 dpi, max scan area 216×297 mm / A4), connected over the same
USB 2.0 cable already used for printing. So on *your* printer, the
capability genuinely exists — this isn't a hypothetical.

**Software path:** Windows exposes scanners through **WIA (Windows Image
Acquisition)**, a COM automation API, the same family of OS-level
machinery that Section 2 of SOURCE_OF_TRUTH.md already leans on for
printing (Windows owns the driver; Python asks Windows to do the work).
Concretely:

```python
import win32com.client   # already available — part of pywin32

# NOTE (compatibility review): win32com.client.constants requires a
# makepy-generated module (gencache), which may not exist — so we avoid it
# entirely and pass WIA's format GUIDs directly. EnsureDispatch additionally
# generates the constants module if named constants are ever preferred.
WIA_FORMAT_PNG = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"  # wiaFormatPNG

device_manager = win32com.client.EnsureDispatch("WIA.DeviceManager")
for info in device_manager.DeviceInfos:
    if info.Type == 1:                 # 1 == scanner device type in WIA
        device = info.Connect()
        item = device.Items(1)         # the flatbed
        image = item.Transfer(WIA_FORMAT_PNG)
        image.SaveFile(r"C:\path\out.png")
```

This mirrors your printing architecture almost exactly, just reversed:

| Printing (existing) | Scanning (proposed) |
|---|---|
| Python → `win32print` → Windows spooler → driver → USB → paper out | Python → `win32com` (WIA) → Windows imaging service → driver → USB → image in |
| `pywin32`, lazily imported inside `app/printer/windows.py` | `pywin32`, lazily imported inside new `app/scanner/windows.py` |
| Windows owns color/paper-handling complexity | Windows owns sensor calibration/driver complexity |

**Constraint check against SOURCE_OF_TRUTH §18:** constraint #11 says
prefer the OS's existing printer/driver system over raw USB control. WIA
*is* that OS-level system for imaging devices — same philosophy, same
justification (Epson's driver already solves calibration correctly; you'd
gain nothing and risk a lot by talking to the scanner's raw USB protocol
yourself). No constraint is violated; this is architecturally the same
decision as "let Windows print, don't touch libusb," applied to scanning.

**Verdict:** 🟢 feasible, 🔵 recommended approach is WIA via `pywin32`,
no new required dependency.

---

## 3. Capability detection — the core requirement you asked for 🔵

This is the part that makes the feature safe to ship to printers/setups
that can't scan, so it gets its own section.

### 3.1 What "detection" means here

A **scanner-capable device** = a WIA `DeviceInfo` entry whose `Type`
property equals `1` (WIA's scanner device type constant). Detection asks
Windows "what imaging devices do you currently see," not "does this
specific printer model support scanning" in the abstract — which is
actually more useful for you: it reflects reality on the exact PC, right
now (driver installed or not, USB plugged in or not), the same way
`GET /printers` already reflects live `win32print` state rather than a
hardcoded model list.

### 3.2 Detection algorithm 🔵

```
1. Try to create WIA.DeviceManager via win32com.client.
   - Any exception (pywin32 missing, WIA service disabled, COM error)
     → capability = False, reason recorded, NO crash, NO effect on /print.
2. Enumerate DeviceInfos. For each entry, read Type.
   - No entries at all → capability = False ("no imaging devices found").
   - Entries exist but none have Type == 1 → capability = False
     ("device present but not a scanner" — e.g. only a webcam).
   - At least one Type == 1 → capability = True, collect Name/DeviceID
     for each.
3. (Best effort) Try to match a scanner's Name against your configured
   printer name (e.g. both containing "L3210") so a future multi-printer
   setup doesn't offer to scan on the wrong device. On a single-printer
   home-lab setup this match is cosmetic — falls back to "list whatever
   WIA reports" if no match is found.
4. Cache the result for the process lifetime (like a startup check), but
   expose it live via GET /scanners so unplugging/replugging the USB
   cable is reflected without restarting the service — re-run the probe
   on each call; it's cheap (COM enumeration only, no actual scan).
```

### 3.3 Where this lives 🔵

New file `app/scanner/windows.py`, structured exactly like
`app/printer/windows.py`:

- `win32com.client` imported **lazily inside functions**, not at module
  top level — this is the same trick SOURCE_OF_TRUTH §13 already credits
  for making CI possible on the Ubuntu runner without a real Windows
  printer; it does the same job here for WIA.
- `list_scan_devices() -> list[ScanDevice]` — never raises; catches
  everything and returns `[]` on any failure, with the failure reason
  logged (not surfaced as an HTTP error).
- `scan_available() -> bool` — thin wrapper, `bool(list_scan_devices())`.

### 3.4 Feature flag, matching the office kill-switch pattern 🔵

`ENABLE_SCAN=1` in `.env` (default on), mirroring `ENABLE_OFFICE` from
the multi-format work: a hard "off" switch independent of hardware
detection, so you can disable the *feature* (e.g. while testing) without
unplugging anything. Both gates are ANDed: scanning is offered only when
`ENABLE_SCAN` is true **and** `scan_available()` is true.

### 3.5 Guarantee to the print path 🔵

- No file under `app/printer/` is modified.
- No file under `app/services/pipeline.py` (the print job pipeline) is
  modified.
- `main.py` gets one additive `app.include_router(scan_router)` line —
  if that router's own startup probe fails, it still mounts (returning
  empty results), it just never breaks app startup.
- The existing 193 print/format tests are untouched and stay green; scan
  gets its own, separate, test file(s).

This satisfies your requirement directly: **a printer with no scanner
behaves identically to the service today** — same endpoints, same
behavior, same reliability — it just won't advertise a Scan option.

---

## 4. API design 🔵

Kept as a parallel, additive surface next to Section 11 of
SOURCE_OF_TRUTH.md — same conventions (job id, `queued` status, polling).

| Endpoint | Method | Request | Response | Why |
|---|---|---|---|---|
| `/scanners` | GET | none | `{"available": true/false, "devices": [{"name": "...", "id": "..."}]}` | Mirrors `/printers`; **this is what the web page checks before showing a Scan button at all.** Never errors — `available:false` and `devices: []` is a normal, healthy response on a scanner-less setup. Read-only GET → stays open without a PIN (same convention as `/printers`/`/jobs` in `app/services/auth.py`). |
| `/scan` | POST | optional: `format` (`pdf` default / `png` / `jpeg`), `color_mode` (`color`/`greyscale`), `dpi` (allowlisted values, e.g. 150/200/300) | `201 {"job_id": "...", "status": "queued"}` — same as `/print`; **503** with a clear message when `ENABLE_SCAN=0` or no scanner is detected (mirrors `/printers`' 503, not 404/409) | Starts a scan job; same "accept immediately, work in a background thread" shape as `/print`. PIN required (state-changing — auth.py convention). |
| `/scan/jobs/{id}` | GET | job id | Status (`queued→scanning→done/failed`) + download link when done | Same polling pattern as `/jobs/{id}`. |
| `/scan/jobs/{id}/download` | GET | job id | The scanned file | Phone downloads/opens the result. |
| `/scan/jobs/{id}` | DELETE | job id | Confirmation | Cancel/cleanup, mirrors `/jobs/{id}` DELETE. PIN required (state-changing). |

**Why a separate `/scan` job table/namespace instead of folding into the
existing print `jobs` table:** the existing store's schema and states
(`received → queued → converting → printing → done/failed/cancelled`)
are print-shaped ("printing" makes no sense for a scan). Keeping scan
jobs in their own small table (or a `direction` column if you'd rather
extend the existing one later) avoids retrofitting print-specific
language onto a fundamentally different job type — consistent with
MULTI_FORMAT_PLAN.md §3's own rule of "isolate behind interfaces, don't
force-fit." (Compatibility review pinned this down: a separate
`scan_jobs` table in the **same** SQLite file (`JOB_DB_PATH`), owned by a
new module `app/services/scan_jobs.py` with **its own connection and its
own `RLock`** — `jobs.py`'s shared connection is never touched, which
keeps the "scan never modifies print code" guarantee literal.)

---

## 5. Scan job lifecycle 🔵

States: `received → scanning → done | failed | cancelled` (deliberately
shorter than print's — there's no multi-format conversion step; WIA
either hands back an image or it doesn't).

1. `POST /scan` → check `ENABLE_SCAN` + `scan_available()` → if either is
   false, **503 with a clear message**, not a 500 — this is an expected,
   documented state, not an error condition (mirrors `/printers`' 503 when
   the OS capability is missing — the 404/409 first proposed didn't match
   the codebase's conventions).
2. Create job, return `201 {"job_id": ..., "status": "queued"}` immediately
   (the same status code `/print` uses).
3. Background thread: `scanning` → WIA transfer from the flatbed →
   `downloads/<job_id>.<ext>` → if `format=pdf` (default), wrap the
   transferred image into a single-page PDF using the **same Pillow
   fit-to-page logic already built for the image print processor**
   (`app/processors/images.py`) — reused, not reinvented.
4. `done` → file kept until downloaded or swept by a cleanup pass (same
   pattern as `uploads/`, just a `downloads/` folder).
5. `failed` → common causes: scanner busy/offline, cover open, no paper on
   glass (WIA raises a COM error) → map to a human message, same spirit as
   the print engine's exit-code mapping in MULTI_FORMAT_PLAN.md §10 Phase 6.

**Hardware note:** the L3210 is flatbed-only (no ADF), so v1 is
inherently **one page per scan job** — this isn't a corner we're cutting,
it's what the hardware supports. If the printer is ever swapped for one
with an automatic document feeder, WIA reports feeder capability
separately (`WIA_DPS_DOCUMENT_HANDLING_CAPABILITIES`) and multi-page
scanning becomes a natural ⚪ future extension, not a redesign.

---

## 6. Android / web side 🔵

Same philosophy as SOURCE_OF_TRUTH §6 Option B (mobile web page served by
FastAPI itself — no app, no Android-specific code):

- On page load, the web page calls `GET /scanners`.
- If `available: false` → **the Scan section simply isn't rendered.**
  No greyed-out button, no "not supported" banner cluttering the UI for
  the common case — a printer without a scanner just looks like today's
  print-only page.
- If `available: true` → a "Scan" button appears alongside the existing
  file-picker/Print button, triggers `POST /scan`, polls
  `/scan/jobs/{id}` the same way the existing page presumably polls
  print job status, and shows a "View/Download scan" link on completion.

---

## 7. Security 🔵

Same posture as SOURCE_OF_TRUTH §8 — sensible home-lab defaults, not
enterprise hardening:

- LAN-only, same PIN gate as print (`app/services/auth.py`), scoped by the
  codebase's existing convention: **pinned** on the state-changing routes
  (`POST /scan`, `DELETE /scan/jobs/{id}`), **open** on read-only GETs
  (`/scanners`, `/scan/jobs/{id}`) — the web page must be able to ask
  "should the Scan section render at all?" without knowing a PIN.
- `dpi` and `color_mode` validated against a **strict allowlist**, not
  passed through raw — mirrors the print side's Phase 7 rule ("strict
  allowlist regex before it touches a command line") applied here to WIA
  property values instead of a Sumatra command line.
- Scanned files get **server-generated filenames** in `downloads/`, same
  anti-path-traversal reasoning as `uploads/`.
- `downloads/` gets the same startup-sweep-of-leftovers treatment as
  `uploads/`.
- No new attack surface beyond what already exists: still no internet
  exposure, still nothing beyond SQLite, still no auth beyond PIN/LAN.

---

## 8. Phased roadmap 🔵

Following the same Phase-0-spike-first convention as MULTI_FORMAT_PLAN.md
§10/§14 — hardware truth before code, paper/glass truth before "done."

### Phase 0 — hardware spike (run on the actual print-server PC) 🔴

- **S1 — Detection.** Run the WIA enumeration snippet from §2 standalone.
  **PASS =** the L3210 appears with `Type == 1`. Also run it with the
  printer's USB unplugged, or (if convenient) on a machine with no
  scanner at all, to confirm detection returns an empty list cleanly
  instead of throwing — this is the spike that directly proves your
  "must not affect printing when absent" requirement.
- **S2 — Single scan.** Transfer one flatbed page to PNG via WIA.
  **PASS =** a real, legible image file is produced.
- **S3 — PDF wrap.** Feed S2's PNG through the existing image
  fit-to-page Pillow logic. **PASS =** a valid single-page PDF that
  opens correctly.
- **S4 — Concurrent-with-print sanity check.** Confirm a scan job and a
  print job don't collide over the same USB device/spooler state (likely
  fine since they're different Windows subsystems, but worth one real
  test given both share one USB cable to one physical unit).

### Phase 1 — detection only (no scanning yet)

`app/scanner/windows.py` (`list_scan_devices`, `scan_available`),
`GET /scanners`, `ENABLE_SCAN` flag, web page conditionally shows/hides
the Scan section. **Ships something real and testable — "the page
correctly hides Scan on a scanner-less setup" — before any scanning code
exists at all.**

**Landed (2026-09-01):** `app/scanner/windows.py` (`list_scan_devices`,
`scan_available`, `scanning_supported` = the two gates ANDed; lazy
`win32com.client` import; never raises, per-entry resilience),
`app/models/scanning.py` (`ScanDevice`, `ScannersInfo` — scan's own
models, separate from printing's), `app/api/scanners.py`
(`GET /scanners`, never errors, no PIN on the read-only GET),
`ENABLE_SCAN` in config + `.env.example`, one additive router mount in
`main.py`, and the web page's Scan section that renders only when
`/scanners` reports a scanner (its placeholder button is replaced in
Phase 3). Tests: a `fake_win32com` fixture in conftest (mirror of
`fake_win32print`; both `win32com` and `win32com.client` injected),
9 unit tests (found / none / not-a-scanner / COM failure / pywin32
missing / broken entry / name fallback / kill switch) and 5 API tests
pinning the never-500s contract. Suite: 285 tests, 96.7 % coverage,
ruff clean. **Print code untouched** — `app/printer/`, `pipeline.py`,
`jobs.py` byte-for-byte unchanged.

### Phase 2 — basic scan pipeline

`POST /scan` (flatbed, default resolution/color only, PDF output),
job lifecycle + `downloads/`, `/scan/jobs/{id}` + download endpoint.

**Landed (2026-09-01):** `app/scanner/windows.py` grew the scan half —
`scan_flatbed(dest)` (driver-default resolution/color, PNG transfer; the
WIA half that raises does so with phone-readable messages: a HRESULT map
for the common WIA errors — busy/offline/jam/cover — with raw-text
fallback, same spirit as the print side's exit-code catalog) and
`_open_flatbed_item()` (flatbed-preferring item selection, spike-proven).
`app/services/scan_jobs.py`: the separate `scan_jobs` table (same SQLite
file, own connection + own RLock — jobs.py's connection never touched;
`create/get/update_status/cancel_job/recover_interrupted`). Lifecycle:
`queued → scanning → done | failed | cancelled`, cancel checked between
every pipeline stage, a cancelled scan never marked done.
`app/services/scan_pipeline.py`: background daemon thread — WIA transfer →
**real ImageProcessor** (the print side's fit-to-page code, spike-S3
reuse) → `downloads/<job_id>.pdf`, raw PNG deleted on success / kept on
failure. `app/services/downloads.py`: `downloads/` hygiene (server-
generated names, dotfiles survive, startup sweep). `app/api/scan.py`:
`POST /scan` (201 + job id, PIN-gated, 503 with an actionable message
when disabled/scanner-less), `GET /scan/jobs/{id}` (carries
`download_url` when done), `GET /scan/jobs/{id}/download`
(FileResponse), `DELETE /scan/jobs/{id}` (cancel + cleanup, PIN-gated).
`main.py`: downloads sweep + scan recovery in the lifespan, one additive
router mount. Tests: 14 scan-store/downloads unit tests, 9 pipeline tests
(fakes with in-flight gates: COM-error translation, vanished scanner,
corrupt-image wrap failure, cancel-mid-transfer discard), 15 API tests.
Suite: 323 tests, 96.0 % coverage, ruff clean. Print code untouched.

### Phase 3 — web UI polish

Scan button, status polling, download/view link — reusing the existing
page's polling pattern rather than inventing a new one.

### Phase 4 — scan options

`dpi`, `color_mode`, `format=png|jpeg` escape hatch, all strictly
validated — same spirit as the print side's Phase 7 options work.

### ⚪ Explicitly future / out of scope for v1

- Multi-page/ADF scanning (moot on this exact printer; revisit only if
  the hardware changes).
- OCR / searchable-PDF output.
- Any direct USB/raw scanner protocol (rejected for the same reason raw
  USB printing was rejected — SOURCE_OF_TRUTH §4).

---

## 9. Testing plan 🔵

Mirrors the existing suite's core trick (SOURCE_OF_TRUTH §13): fake the
OS boundary, never touch real hardware in CI.

| What | How |
|---|---|
| Detection logic: no devices / devices present but none are scanners / one scanner / WIA raising a COM error | Unit tests with a **fake `win32com.client` module** injected into `sys.modules`, same pattern already used for `win32print` |
| `/scanners` never 500s, regardless of what the fake WIA layer does | API test via `TestClient` |
| `/scan` returns a clear 503 (not 500) when `ENABLE_SCAN=0` or no scanner detected | API test |
| Scan job lifecycle transitions, PDF-wrap reuse of the image processor | Unit tests against fakes, same bounded-polling style as the pipeline-threading tests |
| **Regression guard:** the full existing print/format test suite (267 tests on the `scan-feature` branch) still passes unmodified | Just... run it — no change should be needed |

Same CI gates apply: `ruff check .` + `pytest --cov-fail-under=90`.

---

## 10. Open items requiring the spike (§8 Phase 0)

**Spike run on the print-server PC — 2026-09-01 (`spike_scan.py`, 200 dpi):**

- [x] **S1 (plugged-in) PASS** — WIA sees exactly one imaging device:
      `name='EPSON L3210 Series' type=1` (scanner) — L3210 name match True.
- [x] **S2 PASS** — flatbed PNG at 200 dpi: 11.4 MB in **41.4 s**,
      judged legible on screen.
- [x] **S3 PASS** — the REAL `ImageProcessor` wrapped it into a single-page
      546 KB PDF in **0.6 s** (`%PDF-` magic verified); printed via
      SumatraPDF, accepted by the queue.
- [x] **S4 PASS (2026-09-01, two runs).** Run 1: the print half verified on
      real paper while the scan ran (the script then failed *saving* the
      scan — it reused S2's filename and WIA's `ImageFile.SaveFile` refuses
      to overwrite, `0x80070050 ERROR_ALREADY_EXISTS`; the transfer itself
      had already completed — a spike-script bug, not hardware). Run 2
      (after the filename fix, `--only s4`): scan 11.4 MB in **56.1 s**
      AND the print accepted by the spooler, concurrently, over the one
      USB cable. Scan+print together cost ~35 % more than the scan alone
      (41.4 s) — a useful Phase 2 sizing input, not a blocker.
- [x] **S1 (unplugged) PASS** — with the printer's USB unplugged, WIA
      enumeration returns "WIA sees no imaging devices (clean empty
      result, no crash)" and exits 0. That is the formal proof of the
      plan's hard constraint: **a scanner-less setup degrades cleanly and
      printing is untouched.** (The spike script was also fixed to label
      this expected outcome PASS in its summary instead of FAIL.)
- [ ] Decide the final DPI allowlist: 200 dpi took 41.4 s flatbed-to-file
      (mostly the sensor pass — expect ~150 dpi to be faster). The scan
      job timeout in Phase 2 must be sized against real timings at each
      allowlisted DPI.

---

*This document was compatibility-reviewed against the code (§0) and
approved. Phase 0's spike is CLOSED: S1 (plugged + unplugged), S2, S3 and
S4 all PASS on the real L3210 — the scan feature is proven feasible with
zero new dependencies, and a scanner-less setup is proven safe. Phase 1
(detection) and Phase 2 (basic scan pipeline) have landed. Phase 3 (web
UI: scan button, polling, download link) is the next slice to build.*