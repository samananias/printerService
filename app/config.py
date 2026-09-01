"""
Configuration (Phase 4). Reads the optional ".env" file (see .env.example)
so values can differ per machine without editing code — and without adding
the python-dotenv dependency, whose job is trivial to do by hand at this
scale (Constraint 6: prefer simple technologies).

Order of precedence: real environment variables win over .env, .env wins
over the defaults below.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> dict:
    """Tiny .env parser: 'KEY = value' lines, '#' comments, that's all."""
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


_ENV = _load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str) -> str:
    return os.environ.get(name, _ENV.get(name, default))


# Where uploaded PDFs are stored temporarily (SOURCE_OF_TRUTH Section 10)
UPLOAD_DIR = BASE_DIR / "uploads"

# Section 8: cap upload size so a huge/malicious file can't hurt us
MAX_UPLOAD_MB = int(_get("MAX_UPLOAD_MB", "25"))

# Section 8: optional shared PIN. Empty = auth disabled. Enforced in Phase 8.
API_PIN = _get("API_PIN", "")

# Phase 5: target printer. Empty = whatever Windows calls its default.
PRINTER_NAME = _get("PRINTER_NAME", "")

# Phase 5: explicit path to SumatraPDF.exe. If set, used as-is and nothing
# else is tried (makes misconfiguration loud instead of silently falling back).
SUMATRA_PATH = _get("SUMATRA_PATH", "")

# Every real PDF starts with these 5 bytes — the "magic bytes" check that
# catches renamed/fake files that a mere ".pdf" extension check would miss.
# Consumed by app/detection.py, which generalizes the idea to every format.
PDF_MAGIC = b"%PDF-"

# ------------------------------------------------------------------
# Multi-format printing settings (docs/MULTI_FORMAT_PLAN.md).
# Phase 1 only wires the config; each value becomes load-bearing in the
# phase that needs it (images p11, office p12, print options v2).
# ------------------------------------------------------------------

# Paper size sent to the driver via SumatraPDF's -print-settings
# ("paper=<X>,fit"). Empty (default) = no print-settings flag at all — the
# driver chooses the paper, which is the exact behavior spike T4 proved on
# real paper. Opt in (e.g. A4) only after spike T5 confirmed this driver
# honors the flag. Images are also laid out on this size (A4 when empty).
PAPER_SIZE = _get("PAPER_SIZE", "")

# Office conversion (Phase 3): LibreOffice Headless. ENABLE_OFFICE is the
# kill switch for the old PC — 0 turns office formats off without
# uninstalling anything; they are additionally refused while LibreOffice
# is not installed.
ENABLE_OFFICE = _get("ENABLE_OFFICE", "1").strip().lower() not in ("0", "false", "no")

# Explicit path to soffice.exe. Empty = use the standard install location.
LO_PATH = _get("LO_PATH", "")

# Seconds a file conversion may run before the service kills it (enforced
# by the office processor's subprocess handling; images/text finish in well
# under a second).
CONVERT_TIMEOUT_S = int(_get("CONVERT_TIMEOUT_S", "120"))

# Job history database (Phase 5): SQLite, SOURCE_OF_TRUTH §12's upgrade
# path. Default lives under logs/ (git-ignored). Delete the file to reset
# job history.
JOB_DB_PATH = _get("JOB_DB_PATH", str(BASE_DIR / "logs" / "jobs.sqlite3"))

# ------------------------------------------------------------------
# Scan settings (docs/SCAN_PLAN.md).
# ------------------------------------------------------------------

# Scanning (via Windows' WIA) is optional and additive: it is offered only
# when this flag is on AND Windows actually reports a scanner (SCAN_PLAN
# §3.4). Mirrors ENABLE_OFFICE: 0 turns the feature off without unplugging
# anything, and a scanner-less machine simply never offers it at all —
# printing is unaffected either way.
ENABLE_SCAN = _get("ENABLE_SCAN", "1").strip().lower() not in ("0", "false", "no")
