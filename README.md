<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo/printerservice-logo-dark-bg.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/logo/printerservice-logo.svg">
    <img alt="PrinterService Logo" src="docs/logo/printerservice-logo.svg" width="460">
  </picture>
</p>

<p align="center">
  <strong>Print from your Android phone or any device over Wi-Fi to your USB printer</strong>
</p>

<p align="center">
  <a href="https://github.com/samananias/printerService/actions/workflows/ci.yml">
    <img src="https://github.com/samananias/printerService/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
</p>

A lightweight, self-hosted network printing service built with **Python** and **FastAPI**. It turns any standard USB-connected printer (such as the **Epson L3210**) attached to a Windows PC into a wireless network printer accessible directly from your Android phone or any browser on your local Wi-Fi network—no manufacturer cloud services, vendor apps, or specialized mobile drivers required.

---

## 📖 About The Project

### The Problem
Most entry-level desktop inkjets (like the Epson L3210) connect only via USB and lack built-in Wi-Fi or network capabilities. Mobile printing from Android typically requires proprietary manufacturer cloud apps, AirPrint/IPP hardware support, or complex network setups.

### The Solution
**Printer Service** acts as a lightweight software bridge running on a host Windows PC (even low-spec / old PCs). It exposes a mobile-friendly web application and REST API on your local network. When you select a document or image on your phone, the service accepts the upload, standardizes it into a print-ready PDF via dedicated format processors, and silently submits it to the Windows print queue using **SumatraPDF**. Windows and the official Epson driver handle the low-level USB communication and physical printing.

```text
┌─────────────────────────┐
│  Android Phone / Client │
│   (Browser / Web UI)    │
└────────────┬────────────┘
             │  Wi-Fi (HTTP POST /port 8000)
             ▼
┌─────────────────────────────────────────────────────────────┐
│  Windows Host PC (Printer Service)                          │
│                                                             │
│  1. FastAPI Web Server & REST API (`/`, `/print`, `/jobs`)  │
│  2. Validation & Security (Magic bytes, Size, PIN Auth)     │
│  3. Format Processors (Normalize all inputs to PDF):        │
│     • Images (Pillow) ────► PDF                             │
│     • Office (LibreOffice) ► PDF                            │
│     • TXT / CSV (ReportLab)► PDF                            │
│     • PDF ────────────────► Pass-through                    │
│  4. Print Pipeline & Job Engine (SQLite state tracking)     │
│  5. SumatraPDF CLI (`-print-to` / `-print-settings`)        │
└────────────┬────────────────────────────────────────────────┘
             │  Windows Spooler API
             ▼
┌─────────────────────────┐
│   Windows Print Queue   │
│   Epson L3210 Driver    │
└────────────┬────────────┘
             │  USB Cable
             ▼
┌─────────────────────────┐
│   Epson L3210 Printer   │
│     (Paper Output)      │
└─────────────────────────┘
```

### ✨ Key Features

- **📱 Zero-Install Mobile Printing**: Open `http://<server-ip>:8000` in Chrome/Firefox on your phone to upload and print instantly.
- **📄 Multi-Format Conversion**: Seamlessly print PDFs, Photos/Images, Microsoft Office documents, OpenDocument files, and plain text/CSV tables.
- **⚙️ Configurable Print Options**: Set number of copies (1–99), specific page ranges (e.g., `2-6`, `odd`/`even`), paper sizes (A4, Letter, Legal, Long Bond, A3, A5), and Color vs. Monochrome modes.
- **🛡️ Pre-Flight Hardware Checks**: Queries Windows spooler status flags (`offline`, `out of paper`, `door open`, `jam`) before dispatching jobs, preventing silent print failures.
- **🔄 Robust Job Lifecycle & Recovery**: Durable job tracking backed by SQLite (`logs/jobs.sqlite3`), with one-click **🔁 Retry** for failed jobs and support for cancellation.
- **🔒 Local Network Security**: Restricted to private LAN profiles, optional PIN authentication (`API_PIN`), strict file magic-byte validation, and process-tree cleanup.
- **🧪 Comprehensive Testing**: 190+ automated tests (~97% coverage) with faked OS/spooler boundaries running in CI, accompanied by standalone hardware diagnostic spikes (T1–T7).

### 📁 Supported Formats

| Category | Extensions | Processing Method | Details |
|---|---|---|---|
| **PDF** | `.pdf` | Direct pass-through | Native vector submission via SumatraPDF |
| **Images** | `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.gif`, `.tiff` | Pillow (PIL) | Automatic EXIF orientation, alpha-to-white transparency, centered on page, 300 DPI cap |
| **Office Documents** | `.docx`, `.xlsx`, `.pptx`, `.doc`, `.xls`, `.ppt`, `.odt`, `.ods`, `.odp` | LibreOffice Headless | High-fidelity headless conversion, isolated throwaway profile, honors stored Excel print areas |
| **Text & Data** | `.txt`, `.csv` | ReportLab | TXT formatted with monospace wrapping and pagination; CSV formatted with styled grid borders and headers |

---

## 🗺️ Repo Map

| Path | What it is |
|---|---|
| `app/` | Core application: FastAPI routes, format processors, upload validation, print pipeline, and job engine |
| `app/api/web.py` | Mobile web application (file upload form, options dialog, live job status) served at `/` |
| `tests/` | Pytest test suite: unit tests (OS boundaries faked) and API tests via FastAPI `TestClient` |
| `tests/conftest.py` | Shared test fixtures: isolated job stores, temporary `uploads/`, mock `win32print`, print mocks |
| `spike_print_test.py` | Core hardware diagnostic spike (T1–T4) — validates printer visibility, spooler, and SumatraPDF |
| `spike_t5_images.py` | Image printing spike (T5) — tests image conversion, EXIF rotation, and paper size on real hardware |
| `spike_t6_office.py` | Office document spike (T6) — tests LibreOffice conversion of DOCX, XLSX, and PPTX |
| `spike_t7_text.py` | Text & CSV spike (T7) — tests plain-text wrapping and grid table rendering |
| `allow_firewall_8000.bat` | One-click Windows Firewall script to allow inbound TCP traffic on port 8000 |
| `.env.example` | Configuration template — copy to `.env` for local customizations |
| `requirements.txt` | Production dependencies: FastAPI, Uvicorn, pywin32, Pillow, ReportLab, python-multipart |
| `requirements-dev.txt` | Development & testing tools: pytest, pytest-cov, httpx, ruff |
| `pyproject.toml` | Tool configurations: pytest options, coverage thresholds (90%), ruff linting rules |
| `.github/workflows/ci.yml` | Continuous integration workflow: runs ruff and pytest on Ubuntu runners |
| `uploads/`, `logs/` | Runtime directories for temporary upload processing and rotating logs (`logs/service.log`) |
| `docs/logo/` | Project branding assets: SVG icons and wordmark logos (light & dark backgrounds) |

---

## 📦 1. Installation & Prerequisites

### Server Machine (The Windows PC connected to the printer)

| Requirement | Purpose | Installation Instructions |
|---|---|---|
| **Python 3.12+** | Runs the Python service | Install via winget: `winget install -e --id Python.Python.3.12` or download from [python.org](https://www.python.org/downloads/).<br>Verify: `python --version`<br>*(Note: If typing `python` opens the Microsoft Store: go to **Windows Settings → Apps → Advanced app settings → App execution aliases** and turn **OFF** `python.exe` and `python3.exe`)* |
| **SumatraPDF** | Silent PDF printing engine | Install via winget: `winget install SumatraPDF.SumatraPDF` or download from [sumatrapdfreader.org](https://www.sumatrapdfreader.org). Standard install paths are detected automatically. |
| **Epson L3210 Driver** | Windows printer driver | Ensure Windows can print normally: *Windows Settings → Printers → Epson L3210 → Print test page*. |
| **LibreOffice** *(Optional)* | Office-to-PDF conversion | Required for `.docx`, `.xlsx`, `.pptx`, `.odt`, etc. Without it, office uploads are refused with a friendly message while PDF/image/text printing continues working.<br>Install via the CLI recipe below or from [libreoffice.org](https://www.libreoffice.org). |
| **Windows Firewall Rule** | Allows LAN traffic on port 8000 | Right-click `allow_firewall_8000.bat` → **Run as administrator** (one-time setup), or allow it on the Windows Defender prompt on first run (select *Private networks*). |

#### Installing LibreOffice via CLI (Fast & Scriptable)
Download and run the official MSI installer using PowerShell:

```powershell
curl.exe -L -o "$env:TEMP\LibreOffice.msi" "https://download.documentfoundation.org/libreoffice/stable/26.8.0/win/x86_64/LibreOffice_26.8.0_Win_x86-64.msi"
msiexec /i "$env:TEMP\LibreOffice.msi"
```

A default "Typical" installation installs to `C:\Program Files\LibreOffice\program\soffice.exe`, which the service detects automatically (set `LO_PATH` in `.env` only if installed in a custom path).

### Phone / Client Device
- **Zero installation needed**: Any modern mobile browser (Chrome, Safari, Firefox).
- **Network requirement**: Must be connected to the **same Wi-Fi network** as the server PC (note: guest Wi-Fi networks usually isolate devices and prevent connection).

---

## 🚀 2. One-Time Setup

Clone or copy the repository to your host PC, open a terminal in the project root folder, and follow the instructions for your preferred shell:

### Option A: PowerShell / Command Prompt (CMD)

```powershell
# 1. Create an isolated virtual environment
python -m venv .venv

# 2. Activate the virtual environment
.venv\Scripts\activate

# 3. Install required Python packages
pip install -r requirements.txt

# 4. Create your local configuration file
copy .env.example .env
```

> [!TIP]
> **PowerShell execution policy error with `Activate.ps1`?**
> If script execution is restricted, run this command once and retry activating:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Option B: Git Bash

```bash
# 1. Create an isolated virtual environment
python -m venv .venv

# 2. Activate the virtual environment (use 'source' and forward slashes)
source .venv/Scripts/activate

# 3. Install required Python packages
pip install -r requirements.txt

# 4. Create your local configuration file
cp .env.example .env
```

> [!NOTE]
> **Git Bash Tip:** Always use forward slashes `/` and `source`. In Git Bash, backslashes `\` act as escape characters (so `.venv\Scripts\activate` will fail with "command not found").

---

## ▶️ 3. Running the Service

From the project root folder:

### PowerShell / Command Prompt

```powershell
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

*Or via the direct one-liner (without manual activation):*
```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Git Bash

```bash
source .venv/Scripts/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

*Or via the direct one-liner (without manual activation):*
```bash
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 💡 Runtime Notes
- Keep the terminal window open—the service runs as long as the process is active. Press `Ctrl+C` to stop it.
- `--host 0.0.0.0` is **mandatory** because it instructs the server to listen on all local network interfaces so your phone can reach it.
- A successful startup output looks like: `INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)`
- **Self-Check**: On the host PC, open `http://localhost:8000/health` in your browser to verify it returns `{"status":"ok"}`.

---

## 📱 4. Printing From Your Phone

1. **Find the PC's Local IP Address**:
   - Open Command Prompt/PowerShell on the server PC and run `ipconfig`.
   - Note the **IPv4 Address** (e.g., `192.168.1.5`).
   - *(Recommended)* Set a **DHCP reservation** in your home router settings so this IP address never changes.
2. **Open the Web UI on your Phone**:
   - Make sure your phone is connected to the same Wi-Fi.
   - Open your mobile browser and navigate to `http://<server-ip>:8000` (e.g., `http://192.168.1.5:8000`).
3. **Upload and Print**:
   - Select a document or image (PDF, JPG/PNG/WebP, DOCX/XLSX/PPTX, or TXT/CSV).
   - Tap **Print**.
   - Watch the live progress status:
     `📨 Queued… → ⏳ status: converting… → 🖨️ status: printing… → ✅ Printed to EPSON L3210 Series!`
4. **Formatting Behaviors**:
   - **Images**: Automatically fitted and centered on an A4 page with white margins; camera EXIF orientation is respected.
   - **Office Files**: Converted via LibreOffice headless (typically 10–30s); UI indicates `converting` state during processing.
   - **TXT & CSV**: TXT prints formatted monospace text with automatic line-wrapping; CSV renders a structured, bordered grid table.
5. **Job Retries & Cancellation**:
   - If a job fails (e.g., printer out of paper), the uploaded source file is preserved. Tap the **🔁 Retry** button on the web page or call `POST /jobs/{id}/retry`.
   - Active jobs can be cancelled while queued, converting, or printing (best-effort once handed to the Windows spooler).
6. **Print Options Dialog** (Expandable on the web page):
   - **Copies**: 1 to 99 copies.
   - **Page Range**: Custom ranges (`2-6`, `1,3,5`), `odd`, or `even`.
   - **Paper Size**: A4, Short Bond (Letter), Long Bond (8.5×13 / Folio), Legal, A3, A5.
   - **Color Mode**: Full Color or Monochrome (Black & White).
   - *Options apply across all document formats and are retained when retrying a job.*

### 🌐 API Reference

The service provides a full REST API, also browsable interactively via Swagger UI at `http://<server-ip>:8000/docs`:

| Endpoint | Method | Description |
|---|---|---|
| `/health` | `GET` | Server health check (`{"status": "ok"}`). Ideal for reachability verification. |
| `/printers` | `GET` | Lists all printers detected by Windows via `pywin32`. |
| `/print` | `POST` | Upload and queue a file for printing (accepts optional print settings). |
| `/jobs` | `GET` | Lists recent print jobs and their current execution statuses. |
| `/jobs/{id}` | `GET` | Fetches detailed status and metadata for a specific print job. |
| `/jobs/{id}` | `DELETE` | Cancels an active or queued print job. |
| `/jobs/{id}/retry` | `POST` | Re-dispatches a failed job using its stored upload without re-uploading. |

---

## ⚙️ 5. Configuration (`.env`)

Copy `.env.example` to `.env` to configure optional server settings. All keys are optional—the default configuration is ready for immediate use:

| Key | Default | Description |
|---|---|---|
| `MAX_UPLOAD_MB` | `25` | Maximum allowed upload size in megabytes (larger files rejected with HTTP 413). |
| `API_PIN` | *(empty)* | Optional security PIN. When set, requests require the `X-API-PIN` header (the web interface will display a PIN input field). |
| `PRINTER_NAME` | *(empty)* | Specific Windows printer name to target. If empty, the system default printer is used. |
| `SUMATRA_PATH` | *(empty)* | Custom path to `SumatraPDF.exe`. Leave empty to use automatic standard path detection. |
| `PAPER_SIZE` | *(empty)* | Default paper size token passed to driver (e.g. `A4`). Leave empty to let the Windows driver choose. |
| `ENABLE_OFFICE` | `1` | Enables office file processing (`.docx`, `.xlsx`, `.pptx`, `.odt`). Set to `0` to disable office conversion. |
| `LO_PATH` | *(empty)* | Custom path to LibreOffice `soffice.exe`. Leave empty to use automatic discovery. |
| `CONVERT_TIMEOUT_S` | `120` | Maximum timeout in seconds for LibreOffice conversion before terminating the process tree. |
| `JOB_DB_PATH` | `logs/jobs.sqlite3` | Path to the SQLite job history database. Delete the file at any time to reset job history. |
| `HOST`, `PORT` | `8000` | Reference settings (actual binding host and port are passed via the `uvicorn` CLI command). |

> [!NOTE]
> - **Pre-Flight Checks**: The service verifies spooler status (`offline`, `out of paper`, `door open`, `error`) before dispatching jobs.
> - **SumatraPDF Exit Codes**: Exit codes (2 = corrupt file, 4 = printer not found, 5 = driver error) are translated into clear, human-readable explanations.
> - **Log Management**: Log files in `logs/service.log` automatically rotate at ~1 MB with 2 backup archives kept.

---

## 🩺 6. Diagnostics & Hardware Spikes

If printing ever fails or you want to verify your setup before launching the service, use the standalone diagnostic spike scripts:

### Core Printer Diagnostic (T1–T4)
Run from the project root (requires `pywin32`):

```powershell
python spike_print_test.py
```

This diagnostic systematically checks each layer:
- **T1**: Verifies printer visibility through `win32print`.
- **T2**: Tests RAW text submission to the Windows spooler.
- **T3**: Checks the Windows "print" shell verb.
- **T4**: Tests silent PDF printing through SumatraPDF to the physical printer.
- **Result:** T4 PASS with a printed test page confirms the entire Python → SumatraPDF → Spooler → USB chain is functional.

### Multi-Format Acceptance Spikes
- **`spike_t5_images.py`**: Tests ImageProcessor conversion (JPEG, PNG with transparency, WebP, EXIF orientation) and prints to paper.
- **`spike_t6_office.py`**: Tests OfficeProcessor (DOCX tables, landscape XLSX with print areas, 16:9 PPTX) using LibreOffice.
- **`spike_t7_text.py`**: Tests TextProcessor rendering of wrapped text and CSV tables.

---

## 🖥️ 7. Deploying to the Dedicated Print-Server PC

Follow these steps when setting up the service permanently on your print-server machine:

1. **Install Prerequisites**: Install **Python 3.12+**, **SumatraPDF**, printer drivers, and optionally **LibreOffice** (§1).
2. **Obtain the Code**: Clone the repository with `git clone` or copy the project folder (ensure you delete any existing `.venv` folder before copying).
3. **Set Up Virtual Environment**:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   ```
4. **Configure Firewall**: Run `allow_firewall_8000.bat` **as Administrator** to open TCP port 8000.
5. **Run Diagnostics**: Run `python spike_print_test.py` to confirm physical paper prints successfully.
6. **Start the Server**: Launch the service using the instructions in §3 and verify connectivity from your phone.
7. **Reserve Static IP**: In your home router configuration, create a **DHCP reservation** for the PC's MAC address to keep its IP permanent.
8. **Configure Auto-Start on Boot (Optional via Windows Task Scheduler)**:
   - Open **Task Scheduler** → *Create Task*.
   - **General**: Name the task (e.g., `PrinterService`), check *Run whether user is logged on or not*.
   - **Triggers**: Set trigger to **At startup**.
   - **Actions**: Set action to **Start a program**:
     - *Program/script*: `C:\path\to\printerService\.venv\Scripts\python.exe`
     - *Add arguments*: `-m uvicorn app.main:app --host 0.0.0.0 --port 8000`
     - *Start in*: `C:\path\to\printerService\`

---

## 🛠️ 8. Troubleshooting & Common Issues

| Symptom | Likely Cause | Recommended Fix |
|---|---|---|
| Phone browser hangs / cannot connect | Missing Windows Firewall rule or wrong network | Run `allow_firewall_8000.bat` as Admin (§1). Ensure phone is on the same private Wi-Fi network (not a guest network). |
| `error 10048` on server startup | Port 8000 is already in use | Terminate the conflicting application or start Uvicorn with `--port 8001` (and use port 8001 on the phone). |
| Phone reaches `/health` but print job fails | Printer offline or driver error | Check printer power/cable, verify test print in Windows Settings, and check error messages in `logs/service.log`. |
| Job fails: `SumatraPDF not found` | SumatraPDF is not installed in a standard location | Install SumatraPDF via winget (§1) or set the exact binary path in `SUMATRA_PATH` in `.env`. |
| Job fails: `Printer offline / out of paper` | Pre-flight readiness check failed | Ensure printer is turned on, paper is loaded in tray, and clear any paper jams, then click **🔁 Retry**. |
| Job fails: `Printer not default / not found` | Printer name mismatch | Set the exact printer name under `PRINTER_NAME` in `.env` matching Windows printer settings. |
| Office upload rejected: `LibreOffice not installed` | Missing LibreOffice or `ENABLE_OFFICE=0` | Install LibreOffice (§1) or verify `ENABLE_OFFICE=1` in `.env`, then restart the service. |
| Office conversion fails: `Timeout after 120 s` | Large or complex document | Increase `CONVERT_TIMEOUT_S` in `.env` or export to PDF directly on your client device. |
| Office print layout looks altered (fonts/margins) | Missing server-side fonts or missing print area | Install standard font packs on Windows server; for spreadsheets, define an explicit Print Area in Excel. |
| SumatraPDF fails with exit codes `2`, `4`, or `5` | File corrupt (`2`), printer missing (`4`), or driver error (`5`) | Review detailed logs in `logs/service.log` and verify the PDF renders in SumatraPDF directly. |
| Server IP address changes after PC reboot | Dynamic DHCP re-assignment | Set a static IP or configure a DHCP reservation on your home router (§7). |

> [!TIP]
> **Recommended Debugging Hierarchy**: Always diagnose issues from the bottom up:
> 1. Physical Hardware & Drivers (USB cable, paper, Windows test page)
> 2. Network Connectivity (IP address, ping, same Wi-Fi subnet)
> 3. Firewall & Ports (Inbound rules on port 8000)
> 4. Application Logic & Service Logs (`logs/service.log`, `http://localhost:8000/health`)

---

## 🧪 9. Running Tests & Developer Checks

Verify code quality and ensure test coverage before committing changes (mirrors CI workflow):

### PowerShell / Command Prompt
```powershell
.venv\Scripts\activate
pip install -r requirements-dev.txt   # Install testing dependencies (once)
ruff check .                          # Linting: unused imports, style rules, bugs
pytest                                # Executes full test suite with coverage report (≥90% gate)
```

### Git Bash
```bash
source .venv/Scripts/activate
pip install -r requirements-dev.txt   # Install testing dependencies (once)
ruff check .                          # Linting: unused imports, style rules, bugs
pytest                                # Executes full test suite with coverage report (≥90% gate)
```

### Test Architecture Highlights
- **Unit Tests (`tests/unit/`)**: Verify file validation, magic-byte detection, format processors, and pipeline state transitions with all OS interactions (subprocess, file system, `win32print`) completely faked.
- **API Tests (`tests/api/`)**: Simulate real client and phone requests against FastAPI endpoints using `httpx` and `TestClient` without network overhead.
- **Hardware Isolation**: Automated tests never touch the real printer or filesystem state, enabling the exact same test suite to run identically on Windows development machines and Ubuntu CI runners.
- **CI Automation**: GitHub Actions runs `ruff check` and `pytest` with a 90% coverage threshold on every push and pull request (`.github/workflows/ci.yml`).

---

## 📚 10. Documentation & References

For deep dives into architectural decisions, roadmap phases, and design rationales, refer to the project documentation:

- **[docs/SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md)**: The authoritative architecture document, technology stack rationale, network security rules, and detailed failure diagnostic guides.
- **[docs/MULTI_FORMAT_PLAN.md](docs/MULTI_FORMAT_PLAN.md)**: Multi-format design record, decision logs (Pillow, LibreOffice, ReportLab), and the T5–T7 spike protocols.
- **[tests/conftest.py](tests/conftest.py)**: Reference for test fixture implementations and Windows printing mocks.
