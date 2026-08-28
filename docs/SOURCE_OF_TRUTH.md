# Printer Service — Source of Truth

**Project:** Android → Network → Python Service → USB → Epson L3210
**Status:** ✅ MVP working end-to-end (spike T4 PASS: real page printed via SumatraPDF; phone → service → paper verified). ✅ Automated test suite (90 tests, 95%+ coverage gate) + ruff lint + GitHub Actions CI — service *logic* is verified on every push; hardware is verified by the spike on the real PC. Living document. Update this file whenever a decision changes.
**Audience:** Beginner learning networking, servers, and Python.
**Quickstart & pre-setup checklist:** see the root [README.md](../README.md).

---

## How to Read This Document

Every claim below is tagged so you know how much to trust it:

- 🟢 **CONFIRMED FACT** — verifiable, stable, safe to build on.
- 🔵 **RECOMMENDED ARCHITECTURE** — our chosen path, but a design choice, not a law of physics.
- 🟡 **POSSIBLE ALTERNATIVE** — valid, but not what we're starting with.
- 🔴 **NEEDS INVESTIGATION** — you must test this on your actual hardware before relying on it.
- ⚪ **FUTURE IMPROVEMENT** — explicitly out of scope for now.

If a future decision conflicts with this document, this document wins until you deliberately edit it.

---

## 1. Project Objective

**What we are building:** a small Python program (a "service") that runs on your old PC and listens on the network. Your Android phone sends it a PDF over Wi-Fi. The Python service hands that PDF to Windows, which sends it out the USB cable to the Epson L3210, which prints it.

**Is this possible?** 🟢 Yes. This is not exotic — it's conceptually the same thing every "wireless printer" does internally, except normally the printer's *own firmware* plays the role your Python service will play. Your L3210 has no network chip, so you're building that missing piece yourself, in software, on the old PC. That's a legitimate and well-trodden home-lab pattern.

**Role of each component:**

| Component | Role |
|---|---|
| **Android phone** | The *client*. It has the file to be printed and initiates the request. It never talks to the printer directly. |
| **Home network (Wi-Fi/router)** | The *transport*. Carries bytes between phone and PC. |
| **Python service (old PC)** | The *bridge/server*. Accepts requests from the network, translates "please print this PDF" into a real Windows print job. This is the piece that doesn't exist yet. |
| **Windows printing system** | The *translator*. Converts a generic print job into the exact byte stream the L3210 understands (via its driver). |
| **USB cable** | The *last-mile transport*. Carries the final printer-specific data from PC to printer. |
| **Epson L3210** | The *actuator*. Physically puts ink on paper. It has no idea a network or a phone exists — as far as it's concerned, a PC sent it a job over USB, exactly like always. |

**Key mental model:** the printer's world ends at USB. Everything about "the network," "the phone," "the app" is a fiction that your PC constructs *before* the data ever reaches the printer. You are not teaching the printer to be a network printer — you're wrapping it in a PC that pretends to be the network-facing part of one.

---

## 2. Current Architecture (Already Built ✅)

```text
Other PC on network
        │  SMB / Windows printer sharing
        ▼
   Old PC (print server)
        │  USB
        ▼
   Epson L3210
```

🟢 **What you've already proven works:** Windows has a built-in print-server capability. When you "share" a printer, Windows exposes it on the network (typically via the **SMB** protocol, the same one used for shared folders) so other Windows PCs can queue jobs to it as if it were local.

**Concepts involved, explained simply:**

- **USB device**: a printer connected by USB isn't automatically "on the network" — it only speaks to the one PC it's plugged into, over that cable. Windows sees it as a **local printer**.
- **Printer driver**: a piece of software Windows uses to translate a generic "print this page" instruction into the exact command language the L3210's print engine understands (positioning, color, resolution, etc.). Without the right driver, Windows can format a job, but the printer won't understand it.
- **Print queue**: a waiting line, maintained by Windows, for jobs sent to a given printer. If you send two jobs at once, Windows queues the second while the first prints. This is what stops jobs from colliding.
- **Network printer (from the sender's point of view)**: any printer another PC can reach over the network, whether or not it's actually plugged into that PC via USB. Your setup makes the L3210 *appear* as a network printer to other Windows machines, even though physically it's a USB peripheral.
- **Server / client**: the *server* is the machine offering a service (here, "accept and print jobs"); the *client* is the machine asking for that service. Your old PC is the server; other PCs are clients.

**Why this works:** Windows-to-Windows printer sharing uses protocols (SMB plus Windows' own print spooler protocol) that are *built into every Windows install*. You didn't write any code — you configured existing OS features to talk to each other. That's why it "just worked."

**Why this isn't yet what you want:** Android does not speak SMB Windows-printer-sharing the way another Windows PC does. Android's printing model expects HTTP/IPP (see Section 3). This is the gap your Python service will fill.

---

## 3. Proposed Architecture (Next Stage) 🔵

```text
Android App / Browser
        │  Wi-Fi
        ▼
   Home Network (router)
        │  HTTP (TCP, port 8000)
        ▼
 Python Printer Service  ← NEW CODE YOU WRITE
        │  hands job to OS
        ▼
   Print Queue (Windows)
        │
        ▼
 Printer Driver (Windows, Epson L3210 driver)
        │  USB
        ▼
   Epson L3210
```

**Why each layer exists:**

- **Wi-Fi / home network**: without a shared network, the phone has no path to reach the PC at all. This is the *transport layer* — it just moves bytes, with no idea what they mean.
- **HTTP over TCP, port 8000**: this is the *application-level agreement* — a language both phone and Python service understand. HTTP is chosen because every platform, including Android (via its browser and standard HTTP libraries), speaks it natively. A "port" is just a numbered mailbox on the PC; port 8000 is where your Python service will be listening. See Section 7 for port details.
- **Python Printer Service**: this is the piece with no OS-level equivalent for your use case — it receives an HTTP request, pulls the PDF out of it, and calls into Windows' printing system. This is 100% code you write.
- **Windows Print Queue / Driver**: reused from Section 2. You are *not* replacing this — you are feeding it, the same way "File → Print" from any Windows app does.
- **USB**: unchanged, physical, already working.

**Protocol choice for phone ↔ Python:**

| Option | What it is | Verdict |
|---|---|---|
| **HTTP REST API** 🔵 chosen | Phone sends a normal HTTP `POST` request with the PDF attached, like uploading a photo to a website. | **Recommended.** Simple, well-documented, every Android HTTP client (or even just a browser `<input type=file>` form) can do it. Also the most educational — you'll directly see requests, responses, and status codes. |
| **WebSocket** 🟡 alternative | A persistent, two-way connection, good for live/streaming updates. | Overkill for "upload one file, get one response." Worth learning *later* if you want live print-progress updates without polling. |
| **Raw TCP socket** 🟡 alternative | You define your own message format from scratch. | Educational in a different way (you'd learn how HTTP itself is built), but reinvents things HTTP already solves. Not recommended as the first step — more valuable as a *later* exercise once you understand HTTP. |
| **IPP (Internet Printing Protocol)** 🟡 alternative, ⚪ possible future upgrade | 🟢 The actual industry-standard protocol real network printers use, and the basis of Apple AirPrint and the Android/Mopria print ecosystem. | Powerful, but has a steeper learning curve and its own message format (built on HTTP, but with a specific binary encoding). Great goal for later if you want the L3210 to show up in Android's native print dialog (see Section 6, Option C). Not the beginner starting point. |

**Recommendation:** start with a plain **HTTP REST API**, built with Python's FastAPI (see Section 4). It's the simplest correct choice and it directly teaches you client/server, requests/responses, and status codes — the concepts you said you want to learn.

---

## 4. Python Tech Stack 🔵

| Technology | What it does | Why needed | Required / Optional | Runs where | Beginner-friendly? |
|---|---|---|---|---|---|
| **FastAPI** | A Python web framework: turns Python functions into HTTP endpoints (e.g. `POST /print`), with automatic request validation and interactive docs. | This *is* your Python printer service's skeleton — it's how you receive HTTP requests from the phone. | **Required** (or Flask, see below) | Server (old PC) | Yes — arguably easier to learn correctly than Flask, because it gives you clear errors when a request is malformed. |
| **Uvicorn** | The actual program that listens on a TCP port and hands incoming HTTP connections to FastAPI. FastAPI describes *what* to do; Uvicorn is the engine that *runs* it. | FastAPI can't run by itself — it needs a server underneath it. | **Required** if using FastAPI | Server | Yes, mostly invisible — you just run `uvicorn app.main:app`. |
| **Flask** | An alternative, older, simpler web framework than FastAPI. | Does the same core job as FastAPI. | **Optional** (choose one, not both) | Server | Yes — even simpler surface area, but you lose FastAPI's automatic validation and docs, meaning you write more manual checking code. |
| **Python standard library (`http.server`)** | Python's built-in, no-install web server. | Could technically build the whole thing with zero dependencies. | **Optional / educational only** | Server | Technically simplest to install, but you'd hand-write request parsing, which teaches HTTP internals at the cost of speed of progress. Good as a *side exercise*, not the main build. |
| **pywin32 (`win32print`, `win32api`)** | Python bindings for Windows' native printing API. Lets Python ask "what printers exist?" and submit jobs to the Windows print spooler. | This is how your Python code talks to the *existing* Windows print queue from Section 2/3, instead of reinventing printer communication. | **Required** on Windows | Server only (Windows-specific) | Moderate — the API is a thin wrapper over old Windows C APIs, so names are unfamiliar, but a handful of functions cover everything you need. |
| **CUPS** | The standard Linux/macOS print server + driver system. | 🟢 Not applicable — your server is Windows, and CUPS doesn't run natively there. | **Not needed** | N/A for this project | N/A |
| **IPP libraries** (e.g. `pyipp`) | Python libraries implementing the IPP protocol client/server side. | Only needed if/when you upgrade to real IPP so Android's native print dialog can discover your service (Section 6, Option C / Section 3's future upgrade). | **Optional, future** | Server (and technically phone, but Android's OS handles IPP client-side itself) | Lower — IPP's binary format is non-trivial. Not for the MVP. |
| **USB libraries** (e.g. `pyusb`) | Let Python talk to raw USB devices directly, bypassing the OS printing stack entirely. | 🔴 **Deliberately avoided.** Per your own constraint (#12) and general good practice, we let Windows' driver handle USB communication. Talking to a printer's raw USB protocol yourself means reimplementing what the manufacturer's driver already does correctly (color management, paper handling, error recovery). | **Not used in MVP** | Server | Hard — this is genuinely advanced and printer-model-specific. |
| **SQLite** | A lightweight, file-based database built into Python (no server process needed). | Only relevant if you need to durably track print job history across restarts. See Section 12 — likely **not needed for v1**. | **Optional, likely skip initially** | Server | Yes, but skip until you feel the need for it. |
| **Pydantic** | Comes bundled with FastAPI; defines the *shape* of data (e.g. "a print job has a filename and a printer name") and validates it automatically. | Prevents malformed requests from crashing your service; also documents your API for free. | **Required if using FastAPI** (included automatically) | Server | Yes — you'll barely notice you're using it beyond writing simple class definitions. |
| **pytest** (+ **pytest-cov**) | The test runner that executes `tests/` and measures which lines actually ran (coverage). | Verifies the service's *logic* on every change without needing the printer — OS boundaries (win32print, subprocess, filesystem) are faked. CI fails below the coverage gate. | **Dev tool** (`requirements-dev.txt`) | Server + CI (runs on any OS) | Yes — the existing suite is the reference for writing more tests. |
| **httpx** | HTTP client library that FastAPI's `TestClient` uses to fake requests. | Lets tests drive the whole app (`POST /print`, `GET /jobs`…) in-process, with no network and no phone. | **Dev tool** (`requirements-dev.txt`) | Server + CI | Yes — invisible until you write API tests. |
| **ruff** | The linter: flags unused imports, undefined names, import-order drift, and other real-bug classes. | Catches mistakes before they run; CI runs it before the test suite. Deliberately *not* used as a formatter — no wholesale reformatting of working code. | **Dev tool** (`requirements-dev.txt`) | Server + CI | Yes. |

**Bottom-line recommended stack for v1 (Windows server):**
`FastAPI` + `Uvicorn` (web layer) + `pywin32` (talks to Windows printing) + in-memory Python data structures (no database yet).

---

## 5. How Printing Actually Works (End-to-End)

Scenario: **you select a PDF on your phone and press Print.**

```text
1. Select PDF (Android)
        ↓
2. Android sends HTTP POST request containing the file (Network)
        ↓
3. Python server receives the file (Python / FastAPI)
        ↓
4. Python validates the file (Python)
        ↓
5. Python asks Windows to print it (pywin32 → Windows Print Spooler)
        ↓
6. Windows creates a print job in the queue (Windows)
        ↓
7. Printer driver converts job to Epson-specific data (Windows)
        ↓
8. Data travels over USB (Hardware)
        ↓
9. Epson L3210 receives and processes the job (Printer firmware)
        ↓
10. Paper comes out
```

**Stage-by-stage explanation:**

1. **Select PDF** — purely on-device; the phone just has a file path/URI to a PDF stored locally or in an app.
2. **Android sends a request** — the phone's HTTP client (or a simple web form in a browser) opens a TCP connection to `<server-ip>:8000` and sends an HTTP `POST` request. The PDF's bytes are included in the request body, similar to attaching a file to a web form.
3. **Python receives the file** — Uvicorn accepts the incoming TCP connection, hands the parsed HTTP request to FastAPI, which routes it to your `/print` function and hands you the uploaded file's raw bytes.
4. **Python validates the file** — before doing anything printer-related, your code should sanity-check: is this really a PDF? Is it a reasonable size? This is cheap insurance against garbage or malicious uploads (see Section 8).
5. **Python asks Windows to print it** — using `pywin32`, you either (a) save the PDF to a temp file and invoke a "print" action Windows already understands for PDFs, or (b) use the Windows print spooler API directly. 🔴 **Needs investigation**: Windows does not have a *built-in* PDF renderer wired into `win32print` the way it does for plain text or images — see the flagged item at the end of this section.
6. **Windows creates a print job** — the same Print Queue mechanism from Section 2 takes over; this is Windows' existing, battle-tested code, not yours.
7. **Printer driver converts the job** — the Epson driver turns the generic job into the exact instructions the L3210's engine expects (this is the same driver already installed from Section 2).
8. **USB transfer** — physical, already proven working.
9. **Printer firmware executes** — outside your control and outside this project's scope; this is Epson's embedded software.
10. **Paper comes out** — success.

**Should Python talk to the USB printer directly, or let the OS handle it?**

🔵 **Recommendation (matches your own constraint #12): let the OS/driver handle it.** Reasons:
- The Epson driver already knows how to correctly drive this exact printer model (color calibration, paper size handling, error states, ink status).
- Talking directly to USB means re-implementing a printer-specific protocol that's undocumented for most consumer inkjets, is fragile across firmware/driver updates, and offers zero benefit for a beginner project — you'd be building a driver, not a printer service.
- Letting Windows do the driver work keeps your Python code focused on the actually new, educational part: the network/API layer.

🔴 **NEEDS INVESTIGATION — flagged explicitly per your instructions:** the exact mechanics of getting a *PDF specifically* (not plain text, not an image) into the Windows print queue from Python is the trickiest technical unknown in this whole project. `win32print` natively handles raw/plain data and driver-level "print jobs," but rendering a PDF's pages into printable output typically requires either:
- Shelling out to a PDF-capable viewer with a "print" verb (e.g., `ShellExecute` with the `"print"` action, which depends on some registered PDF handler such as Adobe Reader, Edge, or SumatraPDF being installed and configured as that handler), **or**
- Using a dedicated PDF-printing helper (community tools exist, e.g. wrappers around SumatraPDF), **or**
- Converting the PDF to a raster/image format first and printing that.

None of these should be assumed to work out of the box on your specific old PC without testing. **Action item:** in Phase 4 of the roadmap (Section 9), your first real experiment should be "can I successfully print a PDF file from Python on this exact PC, using this exact printer, by any method" before designing the rest of the pipeline around a specific technique.

🟢 **SPIKE RESULT (recorded after running `spike_print_test.py`):**
- T1 PASS — printer visible via `win32print`; target `EPSON L3210 Series` (default).
- T2 PASS — RAW text job accepted by the spooler.
- T3 FAIL — `WinError 1155`: no PDF application on the machine registers the Windows "print" verb. Expected on modern Windows; not a driver problem.
- T4 PASS (after installing SumatraPDF at `%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe` — a location the service's standard search already covers) — **a test page physically printed**, confirming the full Python → SumatraPDF → spooler → L3210 → paper chain.

🔵 **Decision:** **SumatraPDF** (`SumatraPDF.exe -print-to "<printer>" -silent <file.pdf>`) is the primary PDF printing method; the print verb remains a code fallback (default printer only); PDF→image conversion is the unimplemented last resort. Implemented in `app/printer/windows.py`; submission runs in a background thread (`app/services/pipeline.py`) so `POST /print` returns `"queued"` immediately and job status moves `queued → done/failed`. **Status: confirmed working end-to-end via the spike (real page printed).** Re-confirm on the old PC at deploy time.

---

## 6. Android Side

### Option A — Native Android App
```text
Android App → Python API → Printer
```
The app has full UI control, can integrate with Android's file picker, and can show polished status updates. 🟡 Requires learning Android app development (Kotlin/Java) in addition to everything else — a second full skill track on top of Python and networking.

### Option B — Mobile Web Application 🔵 Recommended starting point
```text
Android Browser → Python Web Server → Printer
```
Your FastAPI service itself can serve a simple HTML page (a file picker + "Print" button). The phone just opens a URL like `http://192.168.1.10:8000` in Chrome. No app to install, no Android-specific code, and you're reusing the exact same HTTP knowledge from Section 3.

**Why this is the right starting point:** it removes an entire technology stack (Android app development) from your learning path *for now*, letting you focus fully on the networking/Python/printing chain — which is the actual goal of this project. You can revisit Option A later once the core pipeline works.

### Option C — Android Print Service (native OS integration)
```text
Any Android App → "Print" (native dialog) → Your PrintService → Printer
```
🟢 **Confirmed as a real Android framework** (`android.printservice`, available since Android 4.4/KitKat): Android supports plugin components ("print services") that let the system discover and use your printer from the standard Android print dialog in *any* app, not just yours. This is how real network/AirPrint-style printers integrate.

🔴 **Needs investigation / significantly more advanced:** implementing a `PrintService` means writing real Android platform code (still requires app development skills as in Option A), handling Android's printer-discovery session lifecycle, and typically expects the backend to speak a standard protocol like **IPP** rather than a custom API. This is best treated as an **explicit future milestone**, not part of the MVP.

**Recommendation:** start with **Option B**. It gets you a working, testable system with the least new surface area, while still exercising every core networking/Python concept you want to learn. Treat Option A and especially Option C as ⚪ future improvements.

---

## 7. Networking Requirements

**What you need on your home network:**

| Requirement | Needed? | Why |
|---|---|---|
| **Router** | 🟢 Already have (implied by existing Wi-Fi/network) | Connects devices and assigns addresses. |
| **Wi-Fi** | 🟢 Required for the phone | The phone's only path onto the network. |
| **Ethernet (for the old PC)** | 🟡 Recommended, not required | More stable/faster than Wi-Fi for a server; avoids Wi-Fi drop causing print failures. Optional if Wi-Fi is reliable enough. |
| **Static IP (or DHCP reservation) for the server** | 🔵 **Recommended** | Explained below. |
| **Firewall allowance for your chosen port** | 🟢 Required | Windows Firewall blocks unsolicited inbound connections by default; you must explicitly allow your service's port. |

**Does the server need a static IP?**

🔵 Yes, effectively. Here's why: your phone needs to know *where* to send requests — that means knowing the server's IP address (e.g., `192.168.1.10`). Most home routers use **DHCP** (Dynamic Host Configuration Protocol) to hand out IP addresses automatically, and by default these can *change* over time (e.g., after the PC restarts). If the old PC's address changes, your phone will suddenly be pointing at the wrong machine.

Two ways to solve this, both acceptable:
- **Static IP** configured directly on the PC (you manually set it, outside DHCP's control).
- **DHCP reservation** configured on the router (the router always hands the *same* address to that PC's network card, but DHCP is still technically doing the assigning). This is usually the easier, less error-prone option, since you don't have to also match the PC's subnet/gateway settings by hand.

**How the phone reaches the service — the full path:**

```text
Android Phone                 Router                  Old PC / Server           Printer
192.168.1.20    ─────Wi-Fi────▶   ─────Ethernet/Wi-Fi────▶ 192.168.1.10:8000   ──USB──▶ Epson L3210
```

**Key terms, explained in context:**
- **IP address**: a device's numeric "street address" on the network (e.g., `192.168.1.10`). Needed so the router knows which device to deliver bytes to.
- **TCP port**: once bytes arrive at the right *device*, the port number says which *program on that device* should receive them — like an apartment number once you've reached the right building. Your Python service will claim a port (commonly something like `8000`) and nothing else on that PC should also be using it.
- **Private network / local network**: addresses like `192.168.x.x` are only reachable from *within* your home network, not from the internet — this is actually a safety feature (see Section 8).
- **Windows Firewall rule**: Windows blocks unexpected inbound network connections by default. You'll need to add a rule allowing inbound traffic on your chosen port (e.g., TCP 8000), or the phone's requests will simply never arrive, with no error visible on the phone side — a common source of confusion (see Section 14).

---

## 8. Security

This is a home-lab project, so the goal is **sensible defaults**, not enterprise hardening.

- **Should the service be local-network-only?** 🔵 **Yes, by default.** Don't forward the port through your router to the internet. As long as it's local-network-only, the "attack surface" is limited to devices already trusted enough to be on your Wi-Fi.
- **Should authentication be implemented?** 🟡 Optional for a true home-lab MVP where you trust everyone on your network, but a **simple shared PIN/token** (a fixed string the phone must send along with each request) is a cheap, educational first step into authentication concepts, and cheap insurance if a neighbor's device or an IoT gadget ever gets on your Wi-Fi.
- **Should you expose the service to the internet?** 🔴 **No, not for this project.** Beyond the immediate risk, unauthenticated file upload + "please execute a print" is exactly the kind of endpoint attackers scan the internet for. If you ever want *remote* printing later, that's a deliberate ⚪ future project with its own security design (e.g., a VPN into your home network, not a directly exposed port).
- **What if you accidentally expose the API (e.g., misconfigured router)?** Worst case with no auth: anyone who finds the port could send arbitrary files to be printed (a nuisance/paper-waste/DoS risk) or attempt to exploit a bug in your file-handling code. This is why file validation (below) and *not* forwarding the port matter.
- **What firewall rules should you use?** Allow inbound TCP on your chosen port (e.g., 8000), scoped to your **private network profile** in Windows Firewall (not "public"), so it isn't inadvertently exposed if the PC ever joins another network.
- **Should uploaded files be validated?** 🔵 **Yes, always.** At minimum: check the file extension/content type is actually a PDF, and enforce a reasonable maximum file size. This isn't about defending against sophisticated attackers — it's about not crashing your service on a malformed or huge file.
- **How should temporary print files be handled?** Save each upload to a temp folder with a unique name, and delete it after the print job is confirmed sent (or after a set time, as a cleanup safety net). Leaving uploaded files around indefinitely wastes disk space and is unnecessary once printing is done.

---

## 9. Development Roadmap

### Phase 1 — Networking Fundamentals
- Understand IP addresses and how your router assigns them.
- Understand TCP ports and pick one for your service (e.g., 8000).
- Verify Android → PC connectivity: from the phone's browser, can you reach `http://<server-ip>:8000` at all (even before any Python code exists, e.g. testing against a throwaway "hello world" server)?
- Send a basic HTTP request from the phone and observe a response.

### Phase 2 — Python Server
- Install FastAPI + Uvicorn.
- Create a minimal server with one endpoint, e.g. `GET /health`, returning `{"status": "ok"}`.
- Access it successfully from the Android phone's browser.

### Phase 3 — File Transfer
- Add a `POST /print` endpoint that accepts a file upload (don't print yet — just save it to disk and confirm the bytes arrived intact).
- Upload a real PDF from the phone and verify it lands correctly on the server.

### Phase 4 — Printing (the hard/uncertain part — see Section 5's flagged item)
- 🔴 First experiment: manually confirm you can print a PDF from Python *at all* on this exact PC/printer, by any working method, before building around it.
- Detect the installed Epson L3210 via `pywin32` (list available printers).
- Send a real test document from Python to the printer.
- Confirm the existing Windows print queue handles it correctly (mirrors Section 2's behavior).

### Phase 5 — Android Interface
- Build a minimal mobile-friendly HTML page served by FastAPI itself (Section 6, Option B): a file picker + upload button.
- Confirm end-to-end: select PDF on phone → upload → printed.
- Show basic print status/result back to the phone.

### Phase 6 — Reliability
- Track job status (received / printing / done / failed).
- Add error handling (bad file, printer offline, printer busy).
- Basic queue management if multiple jobs arrive close together.
- Logging, and automatic cleanup of temp files.

---

## 10. Project Folder Structure 🔵

```text
printerService/
├── app/                      # The service
│   ├── main.py               # FastAPI app entry — wires routers, /health, startup sweep
│   ├── config.py             # Tiny .env parser + settings constants
│   ├── api/                  # Routes: print.py, jobs.py, printers.py, web.py (the phone page)
│   ├── printer/              # windows.py — pywin32 detection + SumatraPDF submission
│   ├── services/             # pipeline, job store, upload validation, PIN auth, logging
│   └── models/               # Pydantic request/response shapes (PrintJob, PrintAccepted…)
├── tests/                    # pytest suite: unit/ (logic, OS faked) + api/ (via TestClient)
│   └── conftest.py           # Shared fixtures: fresh job store, temp uploads/, fake win32print
├── .github/workflows/ci.yml  # GitHub Actions: ruff + pytest (+ coverage gate) on every push/PR
├── uploads/                  # Temp storage for incoming PDFs (auto-cleaned)
├── logs/                     # service.log (rotating, ~1 MB × 3)
├── requirements.txt          # Runtime packages: fastapi, uvicorn, python-multipart, pywin32
├── requirements-dev.txt      # Dev packages: pytest, pytest-cov, httpx, ruff
├── pyproject.toml            # Tool config: pytest options, coverage gate, ruff rules
├── spike_print_test.py       # Standalone hardware diagnostic — run on the print-server PC
├── .env                      # Local config values (never committed)
└── README.md                 # Human-facing quickstart instructions
```

Keep it this flat at first — you can split `api/`, `printer/`, etc. further once a folder actually feels crowded. Don't pre-build subfolders you don't have code for yet.

---

## 11. API Design 🔵

| Endpoint | Method | Request | Response | Why it exists |
|---|---|---|---|---|
| `/health` | GET | none | `{"status": "ok"}` | Lets you (or the phone) quickly confirm the server is reachable and running, independent of printing logic — the first thing to check when something's wrong. |
| `/printers` | GET | none | List of available printer names (from `pywin32`) | Confirms Windows/the driver can see the L3210 at all, and leaves room for multiple printers later. |
| `/print` | POST | A file upload (PDF) + optional printer name | `{"job_id": "...", "status": "queued"}` | The core action: accept a file and start a print job. |
| `/jobs` | GET | none | List of recent jobs and their statuses | Lets the phone (or you) see what's happened/is happening, without re-printing. |
| `/jobs/{id}` | GET | job id in URL | Status of one specific job | Lets the UI poll "is my print done yet?" |
| `/jobs/{id}` | DELETE | job id in URL | Confirmation / error | Lets you cancel a queued job — useful once you've accidentally queued the wrong file (you will). |

Nothing here is over-engineered: every endpoint maps directly to something you'll actually need while testing the system by hand in Phase 3–6.

---

## 12. Database 🔵

**Do you need one for v1? No.**

For a single-server, single-user, home-lab MVP, an **in-memory Python dictionary** (job ID → job info) is enough: it's simple, requires no setup, and is easy to reason about while you're still learning. Its one real downside — job history disappears if the service restarts — is not a problem worth solving yet.

- **In-memory storage** 🔵 recommended for v1 — zero setup, perfect for learning, data doesn't survive a restart (acceptable for now).
- **JSON file** 🟡 alternative — barely more effort than in-memory, and survives restarts; reasonable "Phase 6" upgrade if you want job history to persist.
- **SQLite** ⚪ future improvement — worth learning once you actually feel the pain of losing history, or if you want to practice real database concepts (queries, schemas) as a deliberate next-step exercise, not before.

---

## 13. Testing Plan

| # | Test | Type |
|---|---|---|
| 1 | Can the Android phone `ping` the server's IP? | Connectivity (normal) |
| 2 | Can the Android phone reach `GET /health` and see `"ok"`? | API reachability (normal) |
| 3 | Can the Android phone upload a PDF via `POST /print` and get a success response? | Core flow (normal) |
| 4 | Can Python correctly list the Epson L3210 via `pywin32`? | Printer detection (normal) |
| 5 | Can Python successfully send a test PDF that physically prints? | End-to-end (normal) |
| 6 | If two jobs are sent close together, are both queued and printed without corrupting each other? | Concurrency (normal) |
| 7 | What happens if the printer is powered off / USB unplugged when a job is sent? | Failure case |
| 8 | What happens if a non-PDF file (or a corrupted PDF) is uploaded? | Failure case |
| 9 | What happens if the phone is on a different Wi-Fi network / band than the server? | Failure case |
| 10 | What happens if the server's IP address changes (e.g., DHCP reassigns it)? | Failure case |
| 11 | What happens if Windows Firewall blocks the port? | Failure case |

Run the "normal" tests first, in order — each one builds confidence in the layer below it. Only tackle the failure cases once the happy path works end-to-end.

### Automated Test Suite (added after the MVP) ✅

The table above is the *hardware/network* test plan. On top of it sits an automated pytest suite (`tests/`, run by `pytest` from the project root, and by GitHub Actions on every push/PR) that verifies everything which **doesn't require the actual hardware**:

| What the suite verifies | How |
|---|---|
| Upload validation: extension, `%PDF-` magic bytes, size limit — including the exact boundary (`>` vs `>=`) | Unit tests with parametrized inputs (table row #8, automated) |
| Job lifecycle `received → queued → done/failed/cancelled`, error/printer recording, cancellation rules | Unit tests against the in-memory store (row #6's locking, via a concurrency smoke test) |
| Print submission *decisions*: SumatraPDF command line, printer-name override, print-verb fallback and its "default printer only" refusal, loud failure without pywin32 | Unit tests with a **fake `win32print` module** injected into `sys.modules` and mocked `subprocess`/`os.startfile` |
| Whole-API behavior: `/health`, `/`, `/print` (201/401/413/415/500), `/jobs` CRUD, `/printers` (200/503/500) | API tests through FastAPI's `TestClient` — no network needed (rows #2/#3's logic) |
| Pipeline threading: `queued` visible while the thread runs, temp file deleted after `done`, kept after `failed` | Unit tests waiting on fakes with bounded polling (deterministic, no `sleep`) |

**Key design rule:** tests never touch machine state — no real printer, no real SumatraPDF, no real `.env`, real `uploads/` redirected to a temp dir. That's what lets the same suite pass on a Windows dev box and the Ubuntu CI runner. It's possible at all because `win32print` is imported lazily *inside* `app/printer/windows.py`'s functions — a v1 design choice (Section 4) that turned out to make CI possible for free.

**What stays manual:** anything physical or environmental — rows #1, #5, #7, #9, #10, #11, and the "did paper come out" half of #4/#5. `spike_print_test.py` on the actual print-server PC remains the hardware truth (Section 5).

**Quality gates in CI (`.github/workflows/ci.yml`, Ubuntu + Python 3.12):** `ruff check .` (lint only — no formatter enforcement, so working code never gets reformatted wholesale) then `pytest` with `--cov-fail-under=90` (configured in `pyproject.toml`; measured coverage ≈95%, the gap is mostly `logging_setup.py`, which tests deliberately don't execute to keep global logging state pristine). The same two commands run locally from the project root after `pip install -r requirements-dev.txt`.

---

## 14. Common Problems & How to Diagnose Them

| Problem | How to diagnose |
|---|---|
| Windows Firewall blocking the connection | From the phone, `GET /health` times out (not "connection refused" — silently hangs). Check Windows Defender Firewall → Advanced Settings → Inbound Rules for your port. |
| Wrong IP address used | Confirm the server's current IP via `ipconfig` on the PC; compare against what the phone is targeting. |
| Wrong port | Confirm the port Uvicorn is actually listening on matches what the phone is requesting. |
| Phone and PC on different networks (e.g., guest Wi-Fi vs main Wi-Fi, or phone on mobile data) | Check both devices' Wi-Fi network name; guest networks often isolate devices from each other by design. |
| Printer driver problems | Try printing a test page normally from Windows (Settings → Printers) — if that fails too, it's a driver issue unrelated to your code. |
| Printer offline | Check Windows' own printer status icon/queue view; also physically check the printer's display/lights. |
| USB connection problems | Re-seat the cable; check Windows Device Manager for USB errors; try a different USB port. |
| File format problems | Log the uploaded file's size and first few bytes on the server; confirm it's actually a valid PDF before it reaches the printing code. |
| Multiple print jobs at the same time | Check your job-tracking structure (Section 12) — are job IDs colliding? Is the Windows queue showing both jobs? |
| Python service crashing | Check `logs/` for the stack trace; the most common beginner cause is an unhandled exception in the printing code path. |
| Server IP changing due to DHCP | This is the exact problem Section 7's static IP / DHCP reservation recommendation prevents — apply that fix. |
| Printer in use by another application | Check Windows' print queue view for stuck/competing jobs from other programs. |

---

## 15. Beginner Networking Concepts (Taught in Context)

```text
IP Address → Port → TCP → HTTP → API → Server → Client
```

Think of it as **addressing gets progressively more specific**:

1. **IP address** — gets your data to the right *device* on the network (the old PC), the way a street address gets mail to the right *house*.
2. **Port** — once at the right device, gets your data to the right *program* on that device (your Python service, not some other program), like an apartment number within that house.
3. **TCP** — the underlying agreement that guarantees your data actually arrives, in order, without silent corruption or loss, before anything "meaningful" is even discussed. This is the reliable pipe everything else rides on.
4. **HTTP** — a *language* spoken over that reliable TCP pipe: structured requests ("please do X") and responses ("here's the result, and whether it worked"). This is what lets your Python code and the phone's browser/HTTP client understand each other, instead of exchanging meaningless raw bytes.
5. **API** — the specific *vocabulary* of HTTP requests your service understands (`/print`, `/jobs`, etc., from Section 11) — the agreed set of "sentences" your server will respond to.
6. **Server** — the program (your Python service) that *waits* for requests and responds. It's passive until asked something.
7. **Client** — the program (the phone's browser/app) that *initiates* requests. It's active — it decides when to ask.

Every layer depends on the one before it: HTTP is meaningless without a working TCP connection; TCP is meaningless without the data reaching the right port; the port is meaningless without the data reaching the right IP address. When something breaks, this order is also a useful *debugging order* — check connectivity (IP/port) before assuming your API logic is wrong.

---

## 16. What NOT to Build Yet ⚪

Explicitly out of scope for v1:

- Internet access / exposing the service outside your home network
- Cloud deployment of any kind
- Kubernetes
- Docker — unless you specifically want the *learning exercise* of containerizing it later; it adds no functional value here
- Complex authentication (OAuth, user accounts, etc.) — a simple shared PIN, if any, is enough
- Multi-user accounts / permissions
- Cloud database
- Remote printing over the internet
- Advanced monitoring/metrics dashboards
- Load balancing (you have one printer and one server — there is nothing to balance)

Every item above solves a problem you don't have yet. Adding them now would only obscure the actual learning goals of this project.

---

## 17. Recommended MVP

```text
Android Phone
      │  Wi-Fi
      ▼
Simple web page served by Python (Section 6, Option B)
      │  select PDF, tap "Print"
      ▼
POST /print (HTTP, Section 11)
      │
      ▼
Python (FastAPI) receives + validates the PDF
      │
      ▼
pywin32 hands it to the Windows printing system
      │
      ▼
Existing Windows print queue + Epson driver (Section 2, unchanged)
      │  USB
      ▼
Epson L3210 → Printed document
```

This MVP deliberately has **no database, no authentication beyond "same Wi-Fi network," no Android app, and no IPP** — just enough to prove the whole chain works and to genuinely teach you IP addresses, ports, TCP, HTTP, APIs, and the client/server relationship, per Section 15.

---

## 18. Constraints (Do Not Violate Without Updating This Document)

1. Python is the preferred backend language.
2. Printer: Epson L3210, USB-only, no native Wi-Fi/Bluetooth.
3. Server: an old PC, most likely Windows.
4. Android communicates with the server over the local network only.
5. This is a home-lab learning project — not an enterprise product.
6. Prefer simple technologies before complex ones.
7. Don't introduce a technology just because it's popular.
8. Always explain the reasoning behind architectural decisions.
9. Never skip fundamental networking concepts for the sake of speed.
10. Build incrementally — one working slice at a time, per the roadmap in Section 9.
11. Prefer the OS's existing printer/driver system over direct USB control, unless a specific, documented reason emerges to change this.

---

## Open Items Requiring Testing (Summary)

- 🟢 **Resolved (spike run):** the spooler path works and the printer is detected; the Windows "print" verb has no PDF handler on the tested machine, so **SumatraPDF is the chosen PDF method** (Section 5 now records the decision). Still to confirm: T4 PASS after installing SumatraPDF, then a real end-to-end print — on this machine and again on the old PC at deploy time.
- 🔴 Confirm `pywin32` correctly detects and can submit jobs to the specific Epson L3210 driver installed on your PC (Section 4, Section 9 Phase 4). *(Spike T1/T2 confirm detection and spooler acceptance.)*
- 🔴 If you later pursue Option C (Android's native `PrintService` framework, Section 6), treat IPP support and the `PrintService` implementation itself as a separate research phase — do not assume it's a small extension of the MVP.

---

*This document is the project's central reference. When implementation details are decided, update the relevant section here rather than letting decisions live only in code or chat history.*