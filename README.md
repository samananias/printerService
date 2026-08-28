# Printer Service — Print from your Android phone, over Wi-Fi

[![CI](https://github.com/samananias/printerService/actions/workflows/ci.yml/badge.svg)](https://github.com/samananias/printerService/actions/workflows/ci.yml)

**Project:** Android phone → Wi-Fi → Python service (this PC) → Windows print queue → USB → Epson L3210
**Status:** ✅ **MVP working end-to-end** — a phone upload prints real paper. ✅ Logic verified automatically: pytest suite + ruff lint run in CI on every push.
**Full design document:** [docs/SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md) — architecture, concepts, roadmap, testing plan. If it disagrees with this file, it wins.

---

## Repo Map

| Path | What it is |
|---|---|
| `app/` | The service: FastAPI app, upload + print pipeline, job tracking, Windows printing |
| `app/api/web.py` | The mobile web page (file picker + Print button) served at `/` |
| `tests/` | pytest suite — unit tests (OS boundaries faked) + API tests via TestClient |
| `tests/conftest.py` | Shared fixtures: fresh job store, temp `uploads/`, fake `win32print`, print mock |
| `spike_print_test.py` | Standalone printer diagnostic — run it when printing misbehaves |
| `allow_firewall_8000.bat` | One-click firewall rule (run as administrator, once) |
| `.env.example` | Configuration template — copy to `.env` (never committed) |
| `requirements.txt` | Python packages: fastapi, uvicorn, pywin32, python-multipart |
| `requirements-dev.txt` | Dev tools: pytest, pytest-cov, httpx, ruff |
| `pyproject.toml` | Tool config: pytest options, coverage gate (90%), ruff lint rules |
| `.github/workflows/ci.yml` | GitHub Actions: lint + tests on every push/PR (Ubuntu) |
| `uploads/`, `logs/` | Runtime temp files (auto-cleaned) and `logs/service.log` |

---

## 1. What to Install

### The machine that runs the service (the one with printer access)

| Requirement | Why | How |
|---|---|---|
| **Python 3.12+** | Runs the service | `winget install -e --id Python.Python.3.12` or [python.org](https://www.python.org/downloads/). Verify: `python --version`. If typing `python` opens the Microsoft Store: *Settings → Apps → Advanced app settings → App execution aliases* → turn OFF `python.exe` / `python3.exe` |
| **SumatraPDF** | The PDF printing engine — the service hands PDFs to it silently | `winget install SumatraPDF.SumatraPDF` or [sumatrapdfreader.org](https://www.sumatrapdfreader.org). No configuration needed — standard install locations are searched automatically |
| **Epson L3210 driver** | Windows must print normally on its own first | Test: *Settings → Printers → Epson L3210 → Print test page*. If that fails, fix it before anything else |
| **Firewall rule, TCP 8000** | The #1 reason phones "can't connect" | Right-click `allow_firewall_8000.bat` → **Run as administrator** (one time), or accept Windows' pop-up on first run (tick *Private networks*) |

### The phone

Nothing to install — any browser. Same Wi-Fi network as the service PC (guest networks usually isolate devices — a classic silent failure).

---

## 2. One-Time Setup

From the project folder:

```powershell
python -m venv .venv                     # create an isolated Python environment
.venv\Scripts\activate                   # activate it — prompt gains (.venv)
pip install -r requirements.txt          # install fastapi, uvicorn, pywin32, python-multipart
copy .env.example .env                   # local config (see §5; defaults are fine)
```

> PowerShell blocked `Activate.ps1`? Run once, then retry:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
> Git Bash activation: `source .venv/Scripts/activate`

---

## 3. Run the Service

```powershell
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Keep the window open — the service exists only while it runs. `Ctrl+C` stops it.
- `--host 0.0.0.0` is **required** — it means "listen on all network interfaces". Omit it and the phone can never connect.
- No-activation one-liner (works from any terminal, any folder):
  ```powershell
  .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
- Working looks like: `INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)`
- Quick self-check from the same PC: open `http://localhost:8000/health` → `{"status":"ok"}`
- Changed the code? Run **Run the checks** below — same commands CI runs.

---

## 4. Print From the Phone

1. Find the service PC's IP: run `ipconfig`, note the **IPv4 Address** (e.g. `192.168.1.5`). Tip: set a **DHCP reservation** for it in the router so it never changes.
2. On the phone (same Wi-Fi): open `http://<that-ip>:8000`
3. Pick a PDF → tap **Print** → watch the status:
   `📨 Queued… → ⏳ status: queued… → 🖨️ Printed to EPSON L3210 Series!`
4. Paper comes out. Done.

Other endpoints (also browsable interactively at `http://<ip>:8000/docs`):

| Endpoint | What it does |
|---|---|
| `GET /health` | Is the service up? First thing to check when anything seems broken |
| `GET /printers` | Which printers Windows sees (the L3210 should be listed) |
| `POST /print` | Upload a PDF and print it |
| `GET /jobs` | Recent jobs and their statuses |
| `GET /jobs/{id}` | One job's status (what the page polls) |
| `DELETE /jobs/{id}` | Cancel a job that hasn't printed yet |

---

## 5. Configuration (`.env`)

Copy `.env.example` → `.env` and edit. All values are optional; defaults work.

| Key | Default | Meaning |
|---|---|---|
| `MAX_UPLOAD_MB` | `25` | Upload size limit (bigger files are rejected with HTTP 413) |
| `API_PIN` | *(empty)* | If set, printing/cancelling requires the PIN (sent as `X-API-PIN`; the web page has a PIN field). Empty = no auth |
| `PRINTER_NAME` | *(empty)* | Target printer. Empty = Windows' default printer |
| `SUMATRA_PATH` | *(empty)* | Explicit path to `SumatraPDF.exe`. Empty = search standard locations. If set, used as-is (misconfiguration fails loudly) |
| `HOST`, `PORT` | `8000` | Informational — actually pass them on the uvicorn command line (§3) |

---

## 6. Diagnostics: the Printer Spike

If printing ever misbehaves, `spike_print_test.py` checks each link of the chain separately (needs `pip install pywin32` on the machine it runs on):

```powershell
python spike_print_test.py
```

It reports: printer visibility (T1), spooler acceptance (T2), Windows print-verb (T3), SumatraPDF (T4) — with a summary and "what to do with this result" guidance. **T4 passing + paper = the whole chain works.** See SOURCE_OF_TRUTH Section 5 for the recorded results that decided the current design.

---

## 7. Deploying to the Print-Server PC (final step)

1. Install **Python 3.12+** and **SumatraPDF** on that PC (§1)
2. Get the code there: `git clone` / `git pull`, or copy the folder (delete `.venv` first — recreate it there with §2)
3. `pip install -r requirements.txt`, `copy .env.example .env`
4. Run `allow_firewall_8000.bat` **as administrator** on that PC
5. Run `python spike_print_test.py` there once — confirm T1/T2/T4 pass with paper
6. Start the service (§3) and test from the phone using **that PC's IP** (`ipconfig`)
7. Set the router's **DHCP reservation** for that PC so its IP is stable
8. Auto-start on boot (optional): Task Scheduler → *Create Task* → trigger "At startup" → action: `C:\...\printerService\.venv\Scripts\python.exe` with arguments `-m uvicorn app.main:app --host 0.0.0.0 --port 8000`, start-in the project folder

---

## 8. When Something Breaks

| Symptom | Likely cause / fix |
|---|---|
| Phone can't connect at all (page hangs) | Firewall rule missing (§1), or phone on a different Wi-Fi/guest network |
| `error 10048` on startup | Port 8000 taken by another program — close it or use `--port 8001` (and that port on the phone) |
| Phone reaches `/health` but print fails | Read the error on the page or in `logs/service.log`; run the spike (§6) |
| Job `failed`: SumatraPDF not found | Install SumatraPDF (§1) or set `SUMATRA_PATH` in `.env` |
| Job `failed`: printer not default / offline | Check the printer in Windows, print a Windows test page |
| Service IP changed after reboot | Set the router's DHCP reservation (§7 step 7) |

Full troubleshooting table: [docs/SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md) Section 14. Debug in this order — connectivity (IP/port) → firewall → service → printing logic (Section 15 explains why).

---

## Run the Checks (what CI runs)

Changed the service code? Two commands verify the logic — without printing anything:

```powershell
.venv\Scripts\activate
pip install -r requirements-dev.txt   # once per machine
ruff check .                          # lint: unused imports, undefined names, style drift
pytest                                # the suite + coverage report (fails below the 90% gate)
```

- **Unit tests** (`tests/unit/`) exercise validation, job tracking, PIN auth, and the printing decisions with every OS boundary faked — no printer, no SumatraPDF, no network needed.
- **API tests** (`tests/api/`) drive the whole FastAPI app through a test client, the same requests the phone makes.
- Tests never touch machine state (real `uploads/` is redirected to a temp dir), so they run identically on your PC and on CI's Ubuntu runner.
- Real paper **can't** be tested by CI — no printer is attached to it. The spike (§6) stays the hardware test.
- GitHub Actions runs both commands on every push and pull request (`.github/workflows/ci.yml`); the badge at the top shows the latest result.

---

## Where to Go Next

- **Roadmap & current phase** → [docs/SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md) Section 9
- **Why it's built this way** → Sections 3–8 there (protocol choice, tech stack, security, scope)
- **API design** → Section 11 · **Testing plan + how the automated suite fits in** → Section 13
- **How the test fixtures work** → the commented `tests/conftest.py` · **What CI runs** → `.github/workflows/ci.yml`
