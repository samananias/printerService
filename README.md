# Printer Service — Print from your Android phone, over Wi-Fi

**Project:** Android phone → Wi-Fi → Python service (old PC) → USB → Epson L3210
**Status:** 🚧 In development — jobs & printers API (P7) done; printing (P5) pending the old-PC spike. Roadmap: [docs/SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md) Section 9.

This file is the **quickstart**: what to check and install *before* running any setup, and how to run the project.
The deep design document — architecture decisions, networking concepts, roadmap, testing plan, troubleshooting — lives in [**docs/SOURCE_OF_TRUTH.md**](docs/SOURCE_OF_TRUTH.md). When this README and that document disagree, that document wins.

---

## Repo Map

| Path | What it is |
|---|---|
| `app/` | The Python service (FastAPI). Not much here yet — built phase by phase. |
| `spike_print_test.py` | Standalone printer diagnostic. Runs **on the old PC** (see "Before you set up"). |
| `docs/SOURCE_OF_TRUTH.md` | Full design document (architecture, roadmap, concepts, testing). |
| `requirements.txt` | Python packages the project needs. |
| `.env.example` | Template for local config — copy to `.env` (never committed). |
| `uploads/`, `logs/` | Runtime temp files and logs (git-ignored contents). |

---

## Before You Set Up — Checklist

There are **two machines** in this project. Do the checks on the right one.

### A. The development laptop (where you edit code)

- [ ] **Python 3.12+ installed** and real (not the Microsoft Store stub).
  Check in a terminal: `python --version` → should print `Python 3.12.x`.
  If it opens the Microsoft Store instead, install Python from [python.org](https://www.python.org/downloads/) or run `winget install -e --id Python.Python.3.12`. Then disable the fake alias: *Settings → Apps → Advanced app settings → App execution aliases → turn OFF `python.exe` and `python3.exe`*.
- [ ] **Git installed** (`git --version` works).
- [ ] **Phone and computer will share the same Wi-Fi** for testing (same network name — guest networks often isolate devices, which breaks everything silently).

### B. The old PC (the print server the L3210 is plugged into)

- [ ] **Epson L3210 driver installed** and Windows can print a normal test page (*Settings → Bluetooth & devices → Printers & scanners → Epson L3210 → Print test page*). If this fails, fix it first — nothing in this project will print otherwise.
- [ ] **SumatraPDF installed** (free, tiny: [sumatrapdfreader.org](https://www.sumatrapdfreader.org)). Recommended: the most reliable way to print PDFs silently from Python, and the design leans on it.
- [ ] **Python 3.12+ installed** (needed to run the service and the spike script on this PC).
- [ ] **Know its IP address**: run `ipconfig` in a terminal, note the *IPv4 Address* (e.g. `192.168.1.10`).
- [ ] **DHCP reservation set on the router** (recommended) so that IP never changes. In your router's admin page, find "DHCP reservation"/"Address reservation" and pin the old PC's MAC address to a fixed IP. (Alternative: a manually configured static IP on the PC itself — more fiddly.)
- [ ] **Windows Firewall will allow the service port.** Do this when the service first runs (Windows usually pops up an "Allow access" dialog — choose **Private networks**, tick it, Allow). To do it manually instead: *Windows Security → Firewall & network protection → Advanced settings → Inbound Rules → New Rule → Port → TCP 8000 → Allow → check "Private" only*. 🔴 Firewall is the #1 reason the phone can't connect while everything looks fine.

> 🟢 **Why these checks matter:** each one removes a failure mode you'd otherwise hit mid-build. They map to the architecture's requirements in [docs/SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md) Sections 2, 7, 8 and 14.

---

## Setup (development laptop)

From the project root:

```bash
# 1. Create an isolated Python environment for this project
python -m venv .venv

# 2. Activate it
.venv\Scripts\activate          # PowerShell / CMD
source .venv/Scripts/activate   # Git Bash

# 3. Install the project's packages
pip install -r requirements.txt

# 4. Create your local config
cp .env.example .env            # then edit values if you like (port, limits, optional PIN)
```

**Run the service** (once the Phase 2 `/health` endpoint lands; currently scaffold-only):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

⚠️ `--host 0.0.0.0` is not optional — without it the server only listens on "this machine" and your phone can never reach it.

---

## The Printer Spike (one-time, on the old PC) 🎯

Before building the printing feature, we prove a PDF can be printed from Python on the *actual* hardware — this is the project's biggest unknown (see SOURCE_OF_TRUTH Section 5).

1. Copy **`spike_print_test.py`** to the old PC (USB stick, or the repo itself).
2. On the old PC:
   ```bash
   pip install pywin32
   python spike_print_test.py
   ```
3. Load paper, watch the printer, and **record the summary it prints at the end** — which tests passed decides how `app/printer/` is implemented.
4. Report the result back so the decision gets written into the design document.

---

## Where to Go Next

- **Roadmap & current phase** → [docs/SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md) Section 9
- **When something breaks** → Section 14 (Common Problems) there — check connectivity (IP/port) *before* suspecting your code (Section 15 explains why, in that order)
- **API design** → Section 11 · **Testing plan** → Section 13
