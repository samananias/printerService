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

# Every real PDF starts with these 5 bytes — the "magic bytes" check that
# catches renamed/fake files that a mere ".pdf" extension check would miss.
PDF_MAGIC = b"%PDF-"
